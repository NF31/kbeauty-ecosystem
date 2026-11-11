#!/usr/bin/env python3
"""Genere des fichiers BPMN 2.0 valides (avec DI) pour le dossier Phase 0 MIAGE.

Sortie : des .bpmn ouvrables tels quels dans l'extension VS Code bpmn-io
(bpmn-io.vs-code-bpmn-io) ou Camunda Modeler, puis affinables visuellement.
Layout horizontal simple : une colonne = une etape, une bande = une lane.
"""
from __future__ import annotations
import html
import os
from dataclasses import dataclass, field

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
}

EVENT_TYPES = {"startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent"}
GATEWAY_TYPES = {"exclusiveGateway", "parallelGateway"}


@dataclass
class Node:
    id: str
    type: str
    name: str
    lane: str
    col: int


@dataclass
class Flow:
    id: str
    src: str
    tgt: str
    name: str = ""


@dataclass
class Process:
    id: str
    name: str
    pool_id: str
    pool_name: str
    lanes: list[tuple[str, str]]
    nodes: list[Node] = field(default_factory=list)
    flows: list[Flow] = field(default_factory=list)


COL_W = 190
LANE_H = 150
POOL_X = 160
POOL_Y = 80
LANE_LABEL_W = 30


def size_for(t: str) -> tuple[int, int]:
    if t in EVENT_TYPES:
        return 36, 36
    if t in GATEWAY_TYPES:
        return 50, 50
    return 110, 80


def build(proc: Process) -> str:
    lane_index = {lid: i for i, (lid, _) in enumerate(proc.lanes)}
    seen: dict[tuple[str, int], str] = {}
    for n in proc.nodes:
        key = (n.lane, n.col)
        if key in seen:
            raise SystemExit(f"collision de placement {proc.id}: {n.id} et {seen[key]} en {key}")
        seen[key] = n.id
    max_col = max((n.col for n in proc.nodes), default=0)
    pool_w = LANE_LABEL_W + (max_col + 1) * COL_W + 60
    pool_h = len(proc.lanes) * LANE_H

    # --- geometry ---
    geo: dict[str, tuple[int, int, int, int]] = {}
    for n in proc.nodes:
        w, h = size_for(n.type)
        li = lane_index[n.lane]
        cx = POOL_X + LANE_LABEL_W + n.col * COL_W + COL_W // 2
        cy = POOL_Y + li * LANE_H + LANE_H // 2
        geo[n.id] = (cx - w // 2, cy - h // 2, w, h)

    incoming: dict[str, list[str]] = {n.id: [] for n in proc.nodes}
    outgoing: dict[str, list[str]] = {n.id: [] for n in proc.nodes}
    for f in proc.flows:
        outgoing[f.src].append(f.id)
        incoming[f.tgt].append(f.id)

    # --- process XML ---
    lane_xml = []
    for lid, lname in proc.lanes:
        refs = "".join(
            f"\n        <bpmn:flowNodeRef>{n.id}</bpmn:flowNodeRef>"
            for n in proc.nodes
            if n.lane == lid
        )
        lane_xml.append(
            f'      <bpmn:lane id="{lid}" name="{html.escape(lname)}">{refs}\n      </bpmn:lane>'
        )

    node_xml = []
    for n in proc.nodes:
        inc = "".join(f"\n      <bpmn:incoming>{i}</bpmn:incoming>" for i in incoming[n.id])
        out = "".join(f"\n      <bpmn:outgoing>{o}</bpmn:outgoing>" for o in outgoing[n.id])
        node_xml.append(
            f'    <bpmn:{n.type} id="{n.id}" name="{html.escape(n.name)}">{inc}{out}\n    </bpmn:{n.type}>'
        )

    flow_xml = [
        f'    <bpmn:sequenceFlow id="{f.id}" sourceRef="{f.src}" targetRef="{f.tgt}"'
        + (f' name="{html.escape(f.name)}"' if f.name else "")
        + " />"
        for f in proc.flows
    ]

    # --- DI ---
    di_shapes = [
        f'      <bpmndi:BPMNShape id="{proc.pool_id}_di" bpmnElement="{proc.pool_id}" isHorizontal="true">\n'
        f'        <dc:Bounds x="{POOL_X}" y="{POOL_Y}" width="{pool_w}" height="{pool_h}" />\n'
        f'      </bpmndi:BPMNShape>'
    ]
    for i, (lid, _) in enumerate(proc.lanes):
        di_shapes.append(
            f'      <bpmndi:BPMNShape id="{lid}_di" bpmnElement="{lid}" isHorizontal="true">\n'
            f'        <dc:Bounds x="{POOL_X + LANE_LABEL_W}" y="{POOL_Y + i * LANE_H}" '
            f'width="{pool_w - LANE_LABEL_W}" height="{LANE_H}" />\n'
            f'      </bpmndi:BPMNShape>'
        )
    for n in proc.nodes:
        x, y, w, h = geo[n.id]
        label = ""
        if n.type in EVENT_TYPES or n.type in GATEWAY_TYPES:
            label = (
                f'\n        <bpmndi:BPMNLabel>\n'
                f'          <dc:Bounds x="{x - 20}" y="{y + h + 4}" width="{w + 40}" height="27" />\n'
                f'        </bpmndi:BPMNLabel>'
            )
        di_shapes.append(
            f'      <bpmndi:BPMNShape id="{n.id}_di" bpmnElement="{n.id}">\n'
            f'        <dc:Bounds x="{x}" y="{y}" width="{w}" height="{h}" />{label}\n'
            f'      </bpmndi:BPMNShape>'
        )

    di_edges = []
    for f in proc.flows:
        sx, sy, sw, sh = geo[f.src]
        tx, ty, tw, th = geo[f.tgt]
        s_cx, s_cy = sx + sw // 2, sy + sh // 2
        t_cx, t_cy = tx + tw // 2, ty + th // 2
        if abs(s_cy - t_cy) < 10:  # same lane -> horizontal
            p1 = (sx + sw, s_cy)
            p2 = (tx, t_cy)
            wps = [p1, p2]
        elif t_cx >= s_cx:  # forward + lane change -> elbow
            wps = [(sx + sw, s_cy), (tx - 20, s_cy), (tx - 20, t_cy), (tx, t_cy)]
        else:  # loop back
            wps = [(s_cx, sy + sh), (s_cx, sy + sh + 20), (t_cx, ty + th + 20), (t_cx, ty + th)]
        wp_xml = "".join(f'\n        <di:waypoint x="{x}" y="{y}" />' for x, y in wps)
        di_edges.append(
            f'      <bpmndi:BPMNEdge id="{f.id}_di" bpmnElement="{f.id}">{wp_xml}\n'
            f'      </bpmndi:BPMNEdge>'
        )

    lanes_block = "\n".join(lane_xml)
    nodes_block = "\n".join(node_xml)
    flows_block = "\n".join(flow_xml)
    shapes_block = "\n".join(di_shapes)
    edges_block = "\n".join(di_edges)

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="{NS['bpmn']}"
                  xmlns:bpmndi="{NS['bpmndi']}"
                  xmlns:dc="{NS['dc']}"
                  xmlns:di="{NS['di']}"
                  id="defs_{proc.id}"
                  targetNamespace="http://kbeauty.local/bpmn">
  <bpmn:collaboration id="collab_{proc.id}">
    <bpmn:participant id="{proc.pool_id}" name="{html.escape(proc.pool_name)}" processRef="{proc.id}" />
  </bpmn:collaboration>
  <bpmn:process id="{proc.id}" name="{html.escape(proc.name)}" isExecutable="false">
    <bpmn:laneSet id="laneSet_{proc.id}">
{lanes_block}
    </bpmn:laneSet>
{nodes_block}
{flows_block}
  </bpmn:process>
  <bpmndi:BPMNDiagram id="diagram_{proc.id}">
    <bpmndi:BPMNPlane id="plane_{proc.id}" bpmnElement="collab_{proc.id}">
{shapes_block}
{edges_block}
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>
'''


# ---------------------------------------------------------------------------
# Processus A : tunnel d'achat & paiement Stripe (existant, kbeauty-shop)
# ---------------------------------------------------------------------------
checkout = Process(
    id="Process_Checkout",
    name="Tunnel d'achat et paiement Stripe",
    pool_id="Pool_Checkout",
    pool_name="Commande client - kbeauty-shop",
    lanes=[
        ("Lane_Client", "Client (navigateur)"),
        ("Lane_App", "Application Laravel (Inertia)"),
        ("Lane_Stripe", "Stripe"),
        ("Lane_Worker", "Worker asynchrone (Horizon)"),
    ],
    nodes=[
        Node("Ev_Start", "startEvent", "Panier pret,\nclic Commander", "Lane_Client", 0),
        Node("Task_Address", "userTask", "Saisir ou choisir\nles adresses", "Lane_Client", 1),
        Node("Task_Review", "userTask", "Valider le\nrecapitulatif (Payer)", "Lane_Client", 2),
        Node("Task_PlaceOrder", "serviceTask", "Creer Order + Payment\n(statut pending)", "Lane_App", 3),
        Node("Task_CreateSession", "serviceTask", "Creer Checkout Session\nStripe (ui_mode elements)", "Lane_App", 4),
        Node("Task_Confirm", "userTask", "Confirmer le paiement\n(Payment Element)", "Lane_Client", 5),
        Node("Task_StripeProcess", "serviceTask", "Autoriser la carte,\ncreer le PaymentIntent", "Lane_Stripe", 6),
        Node("Ev_Webhook", "intermediateThrowEvent", "checkout.session.completed", "Lane_Stripe", 7),
        Node("Task_VerifySig", "serviceTask", "Verifier la signature,\npersister webhook_call", "Lane_App", 8),
        Node("Gw_Dedup", "exclusiveGateway", "Event deja\ntraite avec succes ?", "Lane_App", 9),
        Node("Task_Job", "serviceTask", "Order=paid, Payment=succeeded,\nrepointer PaymentIntent", "Lane_Worker", 10),
        Node("Task_Fulfil", "serviceTask", "Email confirmation, decrement\nstock, creer Shipment", "Lane_Worker", 11),
        Node("Ev_EndOk", "endEvent", "Commande payee,\npage confirmation", "Lane_Client", 12),
        Node("Ev_EndDup", "endEvent", "Ignore (idempotence)", "Lane_App", 10),
    ],
    flows=[
        Flow("f1", "Ev_Start", "Task_Address"),
        Flow("f2", "Task_Address", "Task_Review"),
        Flow("f3", "Task_Review", "Task_PlaceOrder"),
        Flow("f4", "Task_PlaceOrder", "Task_CreateSession"),
        Flow("f5", "Task_CreateSession", "Task_Confirm"),
        Flow("f6", "Task_Confirm", "Task_StripeProcess"),
        Flow("f7", "Task_StripeProcess", "Ev_Webhook"),
        Flow("f8", "Ev_Webhook", "Task_VerifySig"),
        Flow("f9", "Task_VerifySig", "Gw_Dedup"),
        Flow("f10", "Gw_Dedup", "Task_Job", "non"),
        Flow("f11", "Gw_Dedup", "Ev_EndDup", "oui"),
        Flow("f12", "Task_Job", "Task_Fulfil"),
        Flow("f13", "Task_Fulfil", "Ev_EndOk"),
    ],
)

# ---------------------------------------------------------------------------
# Processus B : circuit asynchrone du diagnostic de peau (montee competence)
# ---------------------------------------------------------------------------
diag = Process(
    id="Process_Diagnostic",
    name="Diagnostic de peau connecte au panier",
    pool_id="Pool_Diagnostic",
    pool_name="Diagnostic de peau - ecosysteme kbeauty",
    lanes=[
        ("LaneD_Client", "Client (navigateur)"),
        ("LaneD_Shop", "kbeauty-shop (Laravel)"),
        ("LaneD_AiCore", "kbeauty-ai-core-service (Spring Boot)"),
        ("LaneD_Ext", "Services externes (Claude, Voyage AI)"),
        ("LaneD_Async", "Consumer RabbitMQ (Laravel)"),
    ],
    nodes=[
        Node("EvD_Start", "startEvent", "Ouvre /diagnostic-peau", "LaneD_Client", 0),
        Node("TaskD_Form", "userTask", "Choisir type de peau,\nenvoyer une photo", "LaneD_Client", 1),
        Node("TaskD_Validate", "serviceTask", "Valider (image, max 8 Mo),\nthrottle 3/60 min", "LaneD_Shop", 2),
        Node("TaskD_Call", "serviceTask", "POST /diagnostics/analyze\n+ X-Internal-Api-Key", "LaneD_Shop", 3),
        Node("GwD_Auth", "exclusiveGateway", "Cle interne\nvalide ?", "LaneD_AiCore", 4),
        Node("EvD_End401", "endEvent", "401, erreur affichee", "LaneD_Client", 4),
        Node("TaskD_Vision", "serviceTask", "Analyse vision\n(image en memoire)", "LaneD_Ext", 5),
        Node("GwD_Photo", "exclusiveGateway", "Photo de\nvisage exploitable ?", "LaneD_AiCore", 6),
        Node("TaskD_Embed", "serviceTask", "Embedding requete +\nrecherche pgvector", "LaneD_Ext", 7),
        Node("TaskD_Persist", "serviceTask", "Persister scores anonymises\n+ ids produits (jamais la photo)", "LaneD_AiCore", 8),
        Node("EvD_Publish", "intermediateThrowEvent", "Publier diagnostic.created\n(RabbitMQ)", "LaneD_AiCore", 9),
        Node("TaskD_Render", "serviceTask", "Rendre la page Inertia :\nanalyse + produits", "LaneD_Shop", 10),
        Node("TaskD_Cart", "userTask", "Ajouter une routine\nau panier", "LaneD_Client", 11),
        Node("EvD_EndOk", "endEvent", "Panier peuple,\ntunnel d'achat", "LaneD_Client", 12),
        Node("EvD_MsgStart", "startEvent", "Message diagnostic.created\nrecu (RabbitMQ)", "LaneD_Async", 9),
        Node("TaskD_Consume", "serviceTask", "Valider le message\ncontre le JSON Schema", "LaneD_Async", 10),
        Node("GwD_Contract", "exclusiveGateway", "Contrat\nrespecte ?", "LaneD_Async", 11),
        Node("EvD_EndLog", "endEvent", "Log info,\nack", "LaneD_Async", 12),
        Node("EvD_EndNack", "endEvent", "Log warning,\nnack sans requeue", "LaneD_Async", 13),
    ],
    flows=[
        Flow("g1", "EvD_Start", "TaskD_Form"),
        Flow("g2", "TaskD_Form", "TaskD_Validate"),
        Flow("g3", "TaskD_Validate", "TaskD_Call"),
        Flow("g4", "TaskD_Call", "GwD_Auth"),
        Flow("g5", "GwD_Auth", "EvD_End401", "non"),
        Flow("g6", "GwD_Auth", "TaskD_Vision", "oui"),
        Flow("g7", "TaskD_Vision", "GwD_Photo"),
        Flow("g8", "GwD_Photo", "TaskD_Embed", "oui"),
        Flow("g9", "GwD_Photo", "TaskD_Persist", "non (pas de matching)"),
        Flow("g10", "TaskD_Embed", "TaskD_Persist"),
        Flow("g11", "TaskD_Persist", "EvD_Publish"),
        Flow("g12", "EvD_Publish", "TaskD_Render"),
        Flow("g13", "TaskD_Render", "TaskD_Cart"),
        Flow("g14", "TaskD_Cart", "EvD_EndOk"),
        Flow("g15", "EvD_MsgStart", "TaskD_Consume"),
        Flow("g16", "TaskD_Consume", "GwD_Contract"),
        Flow("g17", "GwD_Contract", "EvD_EndLog", "oui"),
        Flow("g18", "GwD_Contract", "EvD_EndNack", "non"),
    ],
)

OUT = os.path.dirname(os.path.abspath(__file__))
for proc, fname in [(checkout, "tunnel-achat-stripe.bpmn"), (diag, "diagnostic-peau-async.bpmn")]:
    path = f"{OUT}/{fname}"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build(proc))
    print("ecrit", path)
