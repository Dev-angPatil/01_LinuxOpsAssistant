"""Dynamic System Causality DAG Engine for Multi-Log & Telemetry Root Cause Analysis."""

import re
import time
from typing import List, Dict, Set, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict

@dataclass
class CausalEventNode:
    id: str
    timestamp: float
    subsystem: str
    event_type: str
    description: str
    raw_evidence: str
    confidence: float = 0.90
    in_degree: int = 0
    out_degree: int = 0
    is_root_cause: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class CausalEdge:
    source_id: str
    target_id: str
    relation: str  # e.g., "TRIGGERS", "PRECEDES", "STARVES", "CORRUPTS"
    weight: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class CausalityGraphResult:
    nodes: List[CausalEventNode]
    edges: List[CausalEdge]
    root_cause_nodes: List[CausalEventNode]
    cascade_chain: List[str]
    mermaid_diagram: str
    summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "root_cause_nodes": [n.to_dict() for n in self.root_cause_nodes],
            "cascade_chain": self.cascade_chain,
            "mermaid_diagram": self.mermaid_diagram,
            "summary": self.summary
        }

class CausalityDAGEngine:
    """Builds and analyzes a Directed Acyclic Graph (DAG) of system events to isolate true root causes."""

    # Known causal dependency transitions in Linux systems
    CAUSAL_RULES = [
        # Kernel OOM killer causes process death and socket closure
        ("KERNEL_OOM", "PROCESS_KILLED", "STARVES", 0.98),
        ("PROCESS_KILLED", "SOCKET_CLOSED", "TERMINATES", 0.95),
        ("SOCKET_CLOSED", "UPSTREAM_502", "FAILS_UPSTREAM", 0.92),
        ("SOCKET_CLOSED", "CONNECTION_REFUSED", "FAILS_CONNECT", 0.94),
        
        # Disk full causes log/db write failures and daemon aborts
        ("DISK_EXHAUSTION", "WRITE_FAILURE", "BLOCKS_IO", 0.99),
        ("WRITE_FAILURE", "SERVICE_CRASH", "CORRUPTS_STATE", 0.93),
        ("INODE_EXHAUSTION", "WRITE_FAILURE", "EXHAUSTS_METADATA", 0.95),

        # Port collisions block daemon startup
        ("ROGUE_PROCESS_PORT", "BIND_FAILURE", "COLLIDES_PORT", 0.97),
        ("BIND_FAILURE", "SERVICE_START_FAIL", "PREVENTS_STARTUP", 0.96),

        # Permission errors block config reading
        ("PERMISSION_DENIED", "CONFIG_PARSE_FAIL", "DENIES_ACCESS", 0.92),
        ("CONFIG_PARSE_FAIL", "SERVICE_START_FAIL", "ABORTS_INIT", 0.95),

        # DNS / Network failure
        ("RESOLVER_FAILURE", "TIMEOUT_CONNECT", "CANNOT_RESOLVE", 0.90),
        ("TIMEOUT_CONNECT", "UPSTREAM_502", "LATENCY_SPIKE", 0.91),
    ]

    # Precompiled regex patterns for zero-recompilation log classification
    RE_OOM = re.compile(r"out of memory|oom-killer|killed process \d+|invoked oom-killer", re.IGNORECASE)
    RE_BIND = re.compile(r"address already in use|eaddrinuse|bind\(\) to .* failed", re.IGNORECASE)
    RE_DISK = re.compile(r"no space left on device|enospc|disk full", re.IGNORECASE)
    RE_PERM = re.compile(r"permission denied|eacces", re.IGNORECASE)
    RE_CONN = re.compile(r"connection refused|econnrefused|502 bad gateway|failed to connect", re.IGNORECASE)
    RE_SVC = re.compile(r"failed to start|process exited|unit failed", re.IGNORECASE)

    def __init__(self):
        pass

    def _classify_log_event(self, log_msg: str, source: str, ts: float) -> Optional[CausalEventNode]:
        if self.RE_OOM.search(log_msg):
            return CausalEventNode(
                id=f"oom_{int(ts*1000)%10000}",
                timestamp=ts,
                subsystem="KERNEL_MEM",
                event_type="KERNEL_OOM",
                description="Kernel OOM killer invoked on memory exhaustion",
                raw_evidence=log_msg
            )
        elif self.RE_BIND.search(log_msg):
            return CausalEventNode(
                id=f"bind_{int(ts*1000)%10000}",
                timestamp=ts,
                subsystem="NETWORK_SOCKET",
                event_type="BIND_FAILURE",
                description="Failed to bind listening port (Address already in use)",
                raw_evidence=log_msg
            )
        elif self.RE_DISK.search(log_msg):
            return CausalEventNode(
                id=f"disk_{int(ts*1000)%10000}",
                timestamp=ts,
                subsystem="VFS_STORAGE",
                event_type="DISK_EXHAUSTION",
                description="Filesystem exhausted available physical disk blocks",
                raw_evidence=log_msg
            )
        elif self.RE_PERM.search(log_msg):
            return CausalEventNode(
                id=f"perm_{int(ts*1000)%10000}",
                timestamp=ts,
                subsystem="POSIX_SECURITY",
                event_type="PERMISSION_DENIED",
                description="POSIX permissions blocked access to required path/socket",
                raw_evidence=log_msg
            )
        elif self.RE_CONN.search(log_msg):
            return CausalEventNode(
                id=f"conn_{int(ts*1000)%10000}",
                timestamp=ts,
                subsystem="HTTP_PROXY",
                event_type="UPSTREAM_502",
                description="Upstream connection refused / 502 Bad Gateway downstream symptom",
                raw_evidence=log_msg
            )
        elif self.RE_SVC.search(log_msg):
            return CausalEventNode(
                id=f"svc_{int(ts*1000)%10000}",
                timestamp=ts,
                subsystem="SYSTEMD",
                event_type="SERVICE_START_FAIL",
                description="Systemd service unit exited with failure state",
                raw_evidence=log_msg
            )
        return None

    def build_dag_from_events(self, raw_logs: List[str], base_timestamp: Optional[float] = None) -> CausalityGraphResult:
        """Builds a causality DAG from extracted logs and telemetry metrics."""
        now = base_timestamp or time.time()
        nodes: List[CausalEventNode] = []
        node_map: Dict[str, CausalEventNode] = {}

        # Ingest and classify events with incremental synthetic timestamps to preserve order
        for idx, log_entry in enumerate(raw_logs):
            ts = now - (len(raw_logs) - idx) * 0.5
            node = self._classify_log_event(log_entry, "LOG", ts)
            if node and node.event_type not in [n.event_type for n in nodes]:
                nodes.append(node)
                node_map[node.id] = node

        # If no nodes parsed, create a generic baseline node
        if not nodes:
            default_node = CausalEventNode(
                id="event_root_01",
                timestamp=now,
                subsystem="GENERAL_SYSTEM",
                event_type="UNKNOWN_ANOMALY",
                description="System anomaly detected in standard metrics",
                raw_evidence=raw_logs[0] if raw_logs else "System query inspection",
                is_root_cause=True
            )
            nodes.append(default_node)
            return CausalityGraphResult(
                nodes=nodes,
                edges=[],
                root_cause_nodes=nodes,
                cascade_chain=[default_node.description],
                mermaid_diagram="graph TD\n    A[\"Unknown Anomaly\"]",
                summary="Isolated single system anomaly."
            )

        # Build causal edges based on rules and temporal ordering
        edges: List[CausalEdge] = []
        in_degrees: Dict[str, int] = {n.id: 0 for n in nodes}
        out_degrees: Dict[str, int] = {n.id: 0 for n in nodes}

        for i, src in enumerate(nodes):
            for j, dst in enumerate(nodes):
                if i != j and src.timestamp <= dst.timestamp:
                    for rule_src, rule_dst, relation, weight in self.CAUSAL_RULES:
                        if src.event_type == rule_src and dst.event_type == rule_dst:
                            edges.append(CausalEdge(source_id=src.id, target_id=dst.id, relation=relation, weight=weight))
                            in_degrees[dst.id] += 1
                            out_degrees[src.id] += 1

        # Assign in/out degrees to nodes
        root_causes: List[CausalEventNode] = []
        for n in nodes:
            n.in_degree = in_degrees[n.id]
            n.out_degree = out_degrees[n.id]
            if n.in_degree == 0:
                n.is_root_cause = True
                root_causes.append(n)

        if not root_causes:
            root_causes = [nodes[0]]
            nodes[0].is_root_cause = True

        # Generate topological cascade chain
        cascade_chain = [n.description for n in sorted(nodes, key=lambda x: (not x.is_root_cause, x.timestamp))]

        # Generate Mermaid Graph Definition
        mermaid_lines = ["graph LR"]
        for n in nodes:
            style = ":::rootNode" if n.is_root_cause else ""
            label = f'"{n.subsystem}: {n.description}"'
            mermaid_lines.append(f"    {n.id}[{label}]{style}")
        for e in edges:
            mermaid_lines.append(f"    {e.source_id} -->|{e.relation}| {e.target_id}")
        mermaid_lines.append("    classDef rootNode fill:#ef4444,stroke:#b91c1c,stroke-width:2px,color:#fff;")

        mermaid_str = "\n".join(mermaid_lines)
        summary = f"Root cause identified as: {root_causes[0].description} (InDegree=0, Subsystem={root_causes[0].subsystem})"

        return CausalityGraphResult(
            nodes=nodes,
            edges=edges,
            root_cause_nodes=root_causes,
            cascade_chain=cascade_chain,
            mermaid_diagram=mermaid_str,
            summary=summary
        )
