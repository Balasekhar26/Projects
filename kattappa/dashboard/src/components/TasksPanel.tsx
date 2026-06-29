import React, { useState, useEffect } from 'react';

interface Goal {
  goal_id: string;
  title: string;
  description?: string;
  priority: string;
  priority_score?: number;
  status: string;
  parent_id?: string | null;
  depends_on?: string[];
  max_retries?: number;
  retry_count?: number;
  last_attempt_at?: number | null;
  backoff_delay_sec?: number;
  workspace_snapshot_json?: string | null;
  created_at: number;
}

interface TasksPanelProps {
  goals: Goal[];
  onRefreshGoals: () => void;
  API_BASE: string;
}

export const TasksPanel: React.FC<TasksPanelProps> = ({ goals, onRefreshGoals, API_BASE }) => {
  const [selectedGoalId, setSelectedGoalId] = useState<string | null>(null);
  const [selectedGoalHistory, setSelectedGoalHistory] = useState<any[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Form State
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState('MEDIUM');
  const [parentId, setParentId] = useState('');
  const [dependsOnRaw, setDependsOnRaw] = useState('');
  const [maxRetries, setMaxRetries] = useState(3);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const selectedGoal = goals.find(g => g.goal_id === selectedGoalId) || null;

  useEffect(() => {
    if (selectedGoalId) {
      fetchGoalHistory(selectedGoalId);
    } else {
      setSelectedGoalHistory([]);
    }
  }, [selectedGoalId, goals]);

  const fetchGoalHistory = async (goalId: string) => {
    setLoadingHistory(true);
    try {
      const res = await fetch(`${API_BASE}/goals/${goalId}/history`);
      if (res.ok) {
        const data = await res.json();
        setSelectedGoalHistory(data.history || []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleCreateGoal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setErrorMsg('Goal Title is required');
      return;
    }
    setSubmitting(true);
    setErrorMsg('');
    try {
      const depends_on = dependsOnRaw.split(',').map(s => s.trim()).filter(Boolean);
      const payload = {
        title: title.trim(),
        description: description.trim() || undefined,
        priority,
        parent_id: parentId.trim() || undefined,
        depends_on: depends_on.length > 0 ? depends_on : undefined,
        max_retries: maxRetries
      };

      const res = await fetch(`${API_BASE}/goals`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        setTitle('');
        setDescription('');
        setParentId('');
        setDependsOnRaw('');
        setMaxRetries(3);
        onRefreshGoals();
      } else {
        const err = await res.json();
        setErrorMsg(err.detail || 'Failed to create goal');
      }
    } catch (e: any) {
      setErrorMsg(e.message || 'Network error');
    } finally {
      setSubmitting(false);
    }
  };

  const handleGoalAction = async (goalId: string, action: string) => {
    try {
      const res = await fetch(`${API_BASE}/goals/${goalId}/${action}`, {
        method: 'POST'
      });
      if (res.ok) {
        onRefreshGoals();
      } else {
        const err = await res.json();
        alert(`Error executing action ${action}: ${err.detail || 'Unknown error'}`);
      }
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Top statistics widget */}
      <div className="panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h2 style={{ fontSize: '15px', color: '#fff' }}>🎯 Goals Scheduler Orchestration</h2>
          <div style={{ display: 'flex', gap: '8px' }}>
            <span style={{ fontSize: '11px', background: 'rgba(59, 130, 246, 0.1)', color: 'var(--accent-blue)', padding: '2px 8px', borderRadius: '4px', border: '1px solid rgba(59, 130, 246, 0.2)' }}>
              Active Queue: {goals.filter(g => g.status === 'ACTIVE').length}
            </span>
            <span style={{ fontSize: '11px', background: 'rgba(239, 68, 68, 0.1)', color: 'var(--critical)', padding: '2px 8px', borderRadius: '4px', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
              Blocked: {goals.filter(g => g.status === 'BLOCKED').length}
            </span>
            <span style={{ fontSize: '11px', background: 'rgba(245, 158, 11, 0.1)', color: 'var(--warn)', padding: '2px 8px', borderRadius: '4px', border: '1px solid rgba(245, 158, 11, 0.2)' }}>
              Waiting: {goals.filter(g => g.status === 'WAITING').length}
            </span>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
        {/* Goals Pipeline List */}
        <div className="panel" style={{ flex: '1 1 350px', maxHeight: '600px', overflowY: 'auto' }}>
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">📊</span>
              <h2>Goals Pipeline</h2>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '12px' }}>
            {goals.length === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '12px', padding: '20px' }}>
                No active or scheduled goals in the workspace.
              </div>
            ) : (
              goals.map((g) => {
                const isSelected = selectedGoalId === g.goal_id;
                const statusColor =
                  g.status === 'COMPLETED' ? 'var(--ok)' :
                  g.status === 'ACTIVE' ? 'var(--accent-blue)' :
                  g.status === 'BLOCKED' ? 'var(--critical)' : 'var(--warn)';
                return (
                  <div
                    key={g.goal_id}
                    onClick={() => setSelectedGoalId(g.goal_id)}
                    style={{
                      background: isSelected ? 'rgba(139, 92, 246, 0.1)' : 'rgba(255,255,255,0.01)',
                      border: `1px solid ${isSelected ? 'rgba(139, 92, 246, 0.4)' : 'var(--border)'}`,
                      borderRadius: 'var(--radius-xs)',
                      padding: '12px',
                      cursor: 'pointer',
                      transition: 'all 0.2s'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <span style={{ fontWeight: '600', color: '#fff', fontSize: '13px' }}>{g.title}</span>
                      <span style={{ fontSize: '9px', background: 'rgba(255,255,255,0.05)', padding: '2px 6px', borderRadius: '3px', color: 'var(--text-secondary)' }}>
                        {g.priority}
                      </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px', fontSize: '11px' }}>
                      <span style={{ color: statusColor, fontWeight: 'bold' }}>● {g.status}</span>
                      <span style={{ color: 'var(--text-muted)' }}>ID: {g.goal_id.substring(0, 8)}</span>
                    </div>
                    {g.retry_count && g.retry_count > 0 ? (
                      <div style={{ fontSize: '10px', color: 'var(--warn)', marginTop: '4px' }}>
                        ⚠️ Retry {g.retry_count}/{g.max_retries} (delay: {g.backoff_delay_sec}s)
                      </div>
                    ) : null}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Selected Goal Details */}
        <div className="panel" style={{ flex: '2 1 500px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {selectedGoal ? (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', borderBottom: '1px solid var(--border)', paddingBottom: '12px' }}>
                <div>
                  <h2 style={{ fontSize: '18px', color: '#fff', fontWeight: 'bold' }}>{selectedGoal.title}</h2>
                  <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>{selectedGoal.description || 'No description provided.'}</p>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
                  <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Priority score: {selectedGoal.priority_score?.toFixed(2) || '1.00'}</span>
                  <span style={{ fontSize: '11px', background: 'rgba(255,255,255,0.05)', padding: '2px 8px', borderRadius: '4px', fontWeight: 'bold', color: '#fff' }}>
                    {selectedGoal.status}
                  </span>
                </div>
              </div>

              {/* Dependencies and Parent Hierarchy */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>PARENTS & SUBGOALS</div>
                  <div style={{ fontSize: '12px', color: '#fff', marginTop: '6px' }}>
                    {selectedGoal.parent_id ? `Parent: ${selectedGoal.parent_id.substring(0, 8)}` : 'Root Level Goal'}
                  </div>
                </div>
                <div style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>DEPENDS ON</div>
                  <div style={{ fontSize: '12px', color: '#fff', marginTop: '6px' }}>
                    {selectedGoal.depends_on && selectedGoal.depends_on.length > 0
                      ? selectedGoal.depends_on.map(d => d.substring(0, 8)).join(', ')
                      : 'None'}
                  </div>
                </div>
              </div>

              {/* Workspace snapshot transient state */}
              {selectedGoal.status === 'WAITING' && selectedGoal.workspace_snapshot_json && (
                <div style={{ background: 'rgba(245, 158, 11, 0.05)', padding: '14px', borderRadius: 'var(--radius-xs)', border: '1px solid rgba(245,158,11,0.2)' }}>
                  <div style={{ fontSize: '11px', color: 'var(--warn)', fontWeight: 'bold' }}>💾 Suspended Workspace State Snapshot</div>
                  <pre style={{ margin: '8px 0 0 0', fontSize: '10px', color: '#fcd34d', overflowX: 'auto', background: 'rgba(0,0,0,0.2)', padding: '8px', borderRadius: '4px' }}>
                    {JSON.stringify(JSON.parse(selectedGoal.workspace_snapshot_json), null, 2)}
                  </pre>
                </div>
              )}

              {/* Actions Grid */}
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', borderTop: '1px solid var(--border)', paddingTop: '16px' }}>
                {selectedGoal.status === 'WAITING' && (
                  <>
                    <button
                      onClick={() => handleGoalAction(selectedGoal.goal_id, 'approve')}
                      style={{ padding: '8px 16px', background: 'var(--accent-purple)', border: 'none', borderRadius: 'var(--radius-xs)', color: '#fff', fontWeight: 600, cursor: 'pointer' }}
                    >
                      👍 Approve Goal
                    </button>
                    <button
                      onClick={() => handleGoalAction(selectedGoal.goal_id, 'resume')}
                      style={{ padding: '8px 16px', background: 'var(--ok)', border: 'none', borderRadius: 'var(--radius-xs)', color: '#fff', fontWeight: 600, cursor: 'pointer' }}
                    >
                      ▶️ Resume Execution
                    </button>
                  </>
                )}
                {selectedGoal.status === 'ACTIVE' && (
                  <>
                    <button
                      onClick={() => handleGoalAction(selectedGoal.goal_id, 'suspend')}
                      style={{ padding: '8px 16px', background: 'rgba(245, 158, 11, 0.2)', color: 'var(--warn)', border: '1px solid rgba(245, 158, 11, 0.4)', borderRadius: 'var(--radius-xs)', fontWeight: 600, cursor: 'pointer' }}
                    >
                      ⏸️ Suspend
                    </button>
                    <button
                      onClick={() => handleGoalAction(selectedGoal.goal_id, 'complete')}
                      style={{ padding: '8px 16px', background: 'var(--ok)', border: 'none', borderRadius: 'var(--radius-xs)', color: '#fff', fontWeight: 600, cursor: 'pointer' }}
                    >
                      ✅ Mark Completed
                    </button>
                    <button
                      onClick={() => handleGoalAction(selectedGoal.goal_id, 'abandon')}
                      style={{ padding: '8px 16px', background: 'rgba(239, 68, 68, 0.2)', color: 'var(--critical)', border: '1px solid rgba(239, 68, 68, 0.4)', borderRadius: 'var(--radius-xs)', fontWeight: 600, cursor: 'pointer' }}
                    >
                      🛑 Abandon
                    </button>
                  </>
                )}
              </div>

              {/* History trail */}
              <div style={{ marginTop: '12px' }}>
                <h3 style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px' }}>Execution Event Log</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '150px', overflowY: 'auto' }}>
                  {loadingHistory ? (
                    <div style={{ color: 'var(--text-muted)', fontSize: '11px' }}>Loading...</div>
                  ) : selectedGoalHistory.length > 0 ? (
                    selectedGoalHistory.map((h, i) => (
                      <div key={i} style={{ fontSize: '11px', background: 'rgba(255,255,255,0.01)', border: '1px solid var(--border)', padding: '8px', borderRadius: '4px' }}>
                        <span style={{ color: 'var(--text-muted)' }}>[{new Date(h.timestamp * 1000).toLocaleTimeString()}]</span>{' '}
                        <strong style={{ color: '#fff' }}>{h.event_type}</strong>: {h.payload_json}
                      </div>
                    ))
                  ) : (
                    <div style={{ color: 'var(--text-muted)', fontSize: '11px', fontStyle: 'italic' }}>No events recorded.</div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div style={{ display: 'flex', flex: 1, alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '13px' }}>
              Select a goal from the pipeline to configure execution transitions and review schedules.
            </div>
          )}
        </div>

        {/* Create Goal Form */}
        <div className="panel" style={{ flex: '1 1 300px' }}>
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">🎯</span>
              <h2>Declare New Goal</h2>
            </div>
          </div>
          <form onSubmit={handleCreateGoal} style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '12px' }}>
            <div>
              <label htmlFor="goal-title" style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Goal Title</label>
              <input
                id="goal-title"
                type="text"
                placeholder="Declare system goal objective..."
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                style={{ width: '100%', padding: '8px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', color: '#fff', fontSize: '12px' }}
              />
            </div>
            <div>
              <label htmlFor="goal-desc" style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Description</label>
              <textarea
                id="goal-desc"
                placeholder="Optional detailed description..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                style={{ width: '100%', height: '60px', padding: '8px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', color: '#fff', fontSize: '12px', resize: 'vertical' }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <div>
                <label htmlFor="goal-pri" style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Priority</label>
                <select
                  id="goal-pri"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                  style={{ width: '100%', padding: '8px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', color: '#fff', fontSize: '12px' }}
                >
                  <option value="CRITICAL">CRITICAL</option>
                  <option value="HIGH">HIGH</option>
                  <option value="MEDIUM">MEDIUM</option>
                  <option value="LOW">LOW</option>
                </select>
              </div>
              <div>
                <label htmlFor="goal-retries" style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Max Retries</label>
                <input
                  id="goal-retries"
                  type="number"
                  min="0"
                  max="10"
                  value={maxRetries}
                  onChange={(e) => setMaxRetries(parseInt(e.target.value) || 0)}
                  style={{ width: '100%', padding: '8px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', color: '#fff', fontSize: '12px' }}
                />
              </div>
            </div>
            <div>
              <label htmlFor="goal-parent" style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Parent Goal ID (Optional)</label>
              <input
                id="goal-parent"
                type="text"
                placeholder="Parent UUID..."
                value={parentId}
                onChange={(e) => setParentId(e.target.value)}
                style={{ width: '100%', padding: '8px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', color: '#fff', fontSize: '12px' }}
              />
            </div>
            <div>
              <label htmlFor="goal-deps" style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Depends On Goal IDs (Comma-separated)</label>
              <input
                id="goal-deps"
                type="text"
                placeholder="UUID1, UUID2..."
                value={dependsOnRaw}
                onChange={(e) => setDependsOnRaw(e.target.value)}
                style={{ width: '100%', padding: '8px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: 'var(--radius-xs)', color: '#fff', fontSize: '12px' }}
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              style={{
                width: '100%',
                padding: '10px',
                background: 'linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%)',
                border: 'none',
                borderRadius: 'var(--radius-xs)',
                color: '#fff',
                fontWeight: 600,
                cursor: submitting ? 'not-allowed' : 'pointer'
              }}
            >
              {submitting ? 'Creating Goal...' : '🎯 Create Goal (Proposed)'}
            </button>

            {errorMsg && (
              <div style={{ color: 'var(--critical)', fontSize: '11px', textAlign: 'center', marginTop: '6px' }}>
                ⚠️ {errorMsg}
              </div>
            )}
          </form>
        </div>
      </div>
    </div>
  );
};
