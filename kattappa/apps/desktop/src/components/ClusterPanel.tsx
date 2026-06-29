import type { ClusterRouteResult, ClusterStatus } from "../types";

type ClusterPanelProps = {
  clusterStatus: ClusterStatus | null;
  clusterDraft: { name: string; base_url: string; token: string; capabilities: string };
  clusterDiscoveryDraft: { name: string; base_url: string };
  clusterRouteDraft: { message: string; task_kind: string; sensitivity: string; force_remote: boolean };
  clusterRouteResult: ClusterRouteResult | null;
  clusterError: string;
  onClusterDraftChange: (draft: { name: string; base_url: string; token: string; capabilities: string }) => void;
  onClusterDiscoveryDraftChange: (draft: { name: string; base_url: string }) => void;
  onClusterRouteDraftChange: (draft: { message: string; task_kind: string; sensitivity: string; force_remote: boolean }) => void;
  onRefreshCluster: () => void;
  onRegisterClusterWorker: () => void;
  onDeleteClusterWorker: (nodeId: string) => void;
  onRegisterClusterDiscoveryTarget: () => void;
  onDeleteClusterDiscoveryTarget: (targetId: string) => void;
  onRunClusterRoute: () => void;
};

function statusTone(status: string) {
  const value = status.toLowerCase();
  if (["ready", "done", "completed", "success", "trusted", "installed", "supported"].includes(value)) return "ready";
  if (["approved", "running", "active", "paused", "partial", "degraded", "fallback", "in_progress", "requested", "pending", "draft"].includes(value)) return "working";
  if (["missing", "needs_dependency", "failed", "blocked", "error", "rejected", "disabled", "manual_required"].includes(value)) return "missing";
  return "working";
}

export function ClusterPanel({
  clusterStatus,
  clusterDraft,
  clusterDiscoveryDraft,
  clusterRouteDraft,
  clusterRouteResult,
  clusterError,
  onClusterDraftChange,
  onClusterDiscoveryDraftChange,
  onClusterRouteDraftChange,
  onRefreshCluster,
  onRegisterClusterWorker,
  onDeleteClusterWorker,
  onRegisterClusterDiscoveryTarget,
  onDeleteClusterDiscoveryTarget,
  onRunClusterRoute,
}: ClusterPanelProps) {
  const localNode = clusterStatus?.local_node ?? {};
  const broker = clusterStatus?.broker;
  const privacy = clusterStatus?.privacy_contract ?? {};
  const routeBids = clusterRouteResult?.bid_round?.bids ?? [];
  const routeUnavailable = clusterRouteResult?.bid_round?.unavailable ?? [];

  return (
    <section className="panelView">
      <h2>Cluster</h2>
      <div className="statusGrid">
        <article className="ready">
          <strong>{String(localNode.capability_tier ?? "unknown")}</strong>
          <span>{String(localNode.hostname ?? "local node")}</span>
        </article>
        <article className="ready">
          <strong>{clusterStatus?.paired_nodes.length ?? 0}</strong>
          <span>paired workers</span>
        </article>
        <article className="ready">
          <strong>{clusterStatus?.discovery_targets.length ?? 0}</strong>
          <span>unpaired targets</span>
        </article>
        <article className={broker?.internet_ready ? "ready" : "working"}>
          <strong>{broker?.mode ?? "loading"}</strong>
          <span>{broker?.broadcast_scope ?? "cluster broker"}</span>
        </article>
      </div>

      <h3>Unpaired Discovery</h3>
      <div className="taskComposer">
        <input
          value={clusterDiscoveryDraft.name}
          onChange={(event) => onClusterDiscoveryDraftChange({ ...clusterDiscoveryDraft, name: event.target.value })}
          placeholder="Discovery worker name"
        />
        <input
          value={clusterDiscoveryDraft.base_url}
          onChange={(event) => onClusterDiscoveryDraftChange({ ...clusterDiscoveryDraft, base_url: event.target.value })}
          placeholder="http://192.168.1.20:8000 or https://worker.example.com"
        />
        <div className="taskControls">
          <button onClick={onRegisterClusterDiscoveryTarget}>Add Discovery Target</button>
          <button onClick={onRefreshCluster}>Refresh</button>
        </div>
      </div>
      <div className="scoutList">
        {clusterStatus?.discovery_targets.length ? clusterStatus.discovery_targets.map((target) => (
          <article key={target.id} className="scoutItem ready">
            <header>
              <strong>{target.name}</strong>
              <span>{target.token_required ? "token" : "no pairing"}</span>
            </header>
            <p>{target.base_url}</p>
            <small>Bid receives capability hint only. Task text waits for selected one-time token assignment.</small>
            <div className="scoutActions">
              <button onClick={() => onDeleteClusterDiscoveryTarget(target.id)}>Remove</button>
            </div>
          </article>
        )) : <p>No unpaired discovery targets yet.</p>}
      </div>

      <h3>Paired Workers</h3>
      <div className="taskComposer">
        <input
          value={clusterDraft.name}
          onChange={(event) => onClusterDraftChange({ ...clusterDraft, name: event.target.value })}
          placeholder="Worker name"
        />
        <input
          value={clusterDraft.base_url}
          onChange={(event) => onClusterDraftChange({ ...clusterDraft, base_url: event.target.value })}
          placeholder="http://127.0.0.1:8001 or https://worker.example.com"
        />
        <input
          value={clusterDraft.token}
          onChange={(event) => onClusterDraftChange({ ...clusterDraft, token: event.target.value })}
          placeholder="Pairing token"
          type="password"
        />
        <textarea
          value={clusterDraft.capabilities}
          onChange={(event) => onClusterDraftChange({ ...clusterDraft, capabilities: event.target.value })}
          rows={3}
          placeholder='{"cpu_count_logical": 16, "ram_total_gb": 64}'
        />
        <div className="taskControls">
          <button onClick={onRegisterClusterWorker}>Add Worker</button>
          <button onClick={onRefreshCluster}>Refresh</button>
        </div>
        {clusterError && <p className="formError">{clusterError}</p>}
      </div>

      <div className="scoutList">
        {clusterStatus?.paired_nodes.length ? clusterStatus.paired_nodes.map((node) => (
          <article key={node.id} className="scoutItem ready">
            <header>
              <strong>{node.name}</strong>
              <span>{node.token_configured ? "token set" : "no token"}</span>
            </header>
            <p>{node.base_url}</p>
            <small>{node.runnable_tasks.length ? node.runnable_tasks.join(", ") : "capability profile only"}</small>
            <div className="scoutActions">
              <button onClick={() => onDeleteClusterWorker(node.id)}>Remove</button>
            </div>
          </article>
        )) : <p>No paired workers yet.</p>}
      </div>

      <h3>Bid Route</h3>
      <div className="taskComposer">
        <textarea
          value={clusterRouteDraft.message}
          onChange={(event) => onClusterRouteDraftChange({ ...clusterRouteDraft, message: event.target.value })}
          rows={3}
          placeholder="Task message"
        />
        <div className="taskControls">
          <select
            value={clusterRouteDraft.task_kind}
            onChange={(event) => onClusterRouteDraftChange({ ...clusterRouteDraft, task_kind: event.target.value })}
          >
            <option value="basic_chat">Basic Chat</option>
            <option value="project_memory">Project Memory</option>
            <option value="repo_indexing">Repo Indexing</option>
            <option value="voice_transcription">Voice Transcription</option>
            <option value="small_local_model">Small Local Model</option>
            <option value="large_local_model">Large Local Model</option>
            <option value="simulation">Simulation</option>
            <option value="physical_ai_lab">Physical AI Lab</option>
            <option value="desktop_ui">Desktop UI</option>
            <option value="screen_ocr">Screen OCR</option>
          </select>
          <select
            value={clusterRouteDraft.sensitivity}
            onChange={(event) => onClusterRouteDraftChange({ ...clusterRouteDraft, sensitivity: event.target.value })}
          >
            <option value="normal">Normal</option>
            <option value="private">Private</option>
            <option value="sensitive">Sensitive</option>
          </select>
          <label className="checkField">
            <input
              type="checkbox"
              checked={clusterRouteDraft.force_remote}
              onChange={(event) => onClusterRouteDraftChange({ ...clusterRouteDraft, force_remote: event.target.checked })}
            />
            Force remote
          </label>
          <button onClick={onRunClusterRoute}>Run Bid</button>
        </div>
      </div>

      {clusterRouteResult && (
        <div className="toolResult">
          <header>
            <strong>{clusterRouteResult.status}</strong>
            <span>{clusterRouteResult.run_location}</span>
          </header>
          {clusterRouteResult.worker && <p>{String(clusterRouteResult.worker["name"] ?? "Selected worker")}</p>}
          {clusterRouteResult.message && <p>{clusterRouteResult.message}</p>}
          {clusterRouteResult.selected_bid && (
            <dl>
              <dt>Score</dt>
              <dd>{String(clusterRouteResult.selected_bid.score ?? "n/a")}</dd>
              <dt>Agent</dt>
              <dd>{String(clusterRouteResult.selected_bid.selected_agent ?? "worker")}</dd>
            </dl>
          )}
          <div className="summaryGrid compact">
            <article>
              <strong>{routeBids.length}</strong>
              <span>bids</span>
            </article>
            <article>
              <strong>{routeUnavailable.length}</strong>
              <span>unavailable</span>
            </article>
            <article>
              <strong>{String(clusterRouteResult.worker_result?.cleanup_receipt ? "yes" : "n/a")}</strong>
              <span>cleanup receipt</span>
            </article>
          </div>
          <pre>{JSON.stringify(clusterRouteResult, null, 2)}</pre>
        </div>
      )}

      <h3>Privacy Contract</h3>
      <div className="tagList">
        {Object.entries(privacy).map(([key, value]) => (
          <span key={key}>{key.replace(/_/g, " ")}: {String(value)}</span>
        ))}
      </div>
    </section>
  );
}
