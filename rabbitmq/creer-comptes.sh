#!/usr/bin/env sh
# Comptes RabbitMQ a droits limites (moindre privilege), un par application,
# et l'exchange commun kbeauty.exchange. Rejouable : un compte existant voit
# seulement son mot de passe et ses droits remis a jour.
#
#   ./rabbitmq/creer-comptes.sh
#
# Mots de passe de developpement par defaut ; en production, les passer en
# variables d'environnement :
#   KBEAUTY_SHOP_RABBITMQ_PASSWORD=... SAV_RABBITMQ_PASSWORD=... ./rabbitmq/creer-comptes.sh
#
# Droits RabbitMQ = 3 expressions regulieres sur les noms d'exchanges et de
# files : configure (creer/supprimer), write (publier, lier une file),
# read (consommer, lier depuis un exchange).
set -eu

CONTENEUR=${RABBITMQ_CONTAINER:-kbeauty_rabbitmq}
VHOST=/

ctl() { docker exec "$CONTENEUR" rabbitmqctl -q "$@"; }

compte() { # compte <nom> <mot de passe> <configure> <write> <read>
    if ctl list_users --no-table-headers | cut -f1 | grep -qx "$1"; then
        ctl change_password "$1" "$2"
    else
        ctl add_user "$1" "$2"
    fi
    ctl set_permissions -p "$VHOST" "$1" "$3" "$4" "$5"
    echo "Compte $1 : configure='$3' write='$4' read='$5'"
}

# Exchange commun, declare par l'infrastructure : aucune application n'a
# besoin du droit de le modifier pour l'utiliser (le SAV le verifie
# seulement, en declaration passive).
docker exec "$CONTENEUR" rabbitmqadmin -q declare exchange name=kbeauty.exchange type=direct durable=true

# kbeauty-shop : publie return_request.submitted (outbox) et consomme
# diagnostic.created. Aucun acces aux files du SAV.
compte kbeauty_shop "${KBEAUTY_SHOP_RABBITMQ_PASSWORD:-kbeauty_shop}" \
    '^(kbeauty\.exchange|diagnostic\.created)$' \
    '^(kbeauty\.exchange|diagnostic\.created)$' \
    '^(kbeauty\.exchange|diagnostic\.created)$'

# sav-ticketing-php : possede ses files sav.retours et sav.retours.rejetes,
# lit kbeauty.exchange (pour y lier sa file). Ne peut ni publier sur
# kbeauty.exchange ni le supprimer, ni lire les autres files.
compte sav "${SAV_RABBITMQ_PASSWORD:-sav}" \
    '^sav\.retours(\.rejetes)?$' \
    '^sav\.retours(\.rejetes)?$' \
    '^(kbeauty\.exchange|sav\.retours(\.rejetes)?)$'
