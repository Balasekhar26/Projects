import React, { useState, useEffect } from 'react';

interface PreferenceItem {
  pref_key: string;
  pref_value: any;
  confidence: number;
  evidence_count: number;
  created_at: number;
  updated_at: number;
}

interface MemoryPanelProps {
  cognitiveSnapshot: any;
}

export const MemoryPanel: React.FC<MemoryPanelProps> = ({ cognitiveSnapshot }) => {
  const [preferences, setPreferences] = useState<PreferenceItem[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);
  const [prefKey, setPrefKey] = useState('');
  const [prefVal, setPrefVal] = useState('');
  const [prefConf, setPrefConf] = useState(0.8);

  const fetchPreferences = async () => {
    try {
      const res = await fetch('/api/v1/preferences');
      if (res.ok) {
        const data = await res.json();
        setPreferences(data.items || []);
      }
    } catch (e) {
      console.error('Failed to fetch preferences', e);
    }
  };

  useEffect(() => {
    fetchPreferences();
  }, []);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const res = await fetch(`/api/v1/human-memory/recall?q=${encodeURIComponent(searchQuery)}`);
      if (res.ok) {
        const data = await res.json();
        setSearchResults(data.items || []);
      }
    } catch (e) {
      console.error('Failed to query memory', e);
    } finally {
      setSearching(false);
    }
  };

  const handleCreatePreference = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prefKey.trim() || !prefVal.trim()) return;
    try {
      const res = await fetch('/api/v1/preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          key: prefKey.trim(),
          value: prefVal.trim(),
          confidence: prefConf
        })
      });
      if (res.ok) {
        setPrefKey('');
        setPrefVal('');
        fetchPreferences();
      }
    } catch (e) {
      console.error('Failed to create preference', e);
    }
  };

  const handleReinforce = async (key: string, positive: boolean) => {
    try {
      const res = await fetch('/api/v1/preferences/reinforce', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, positive })
      });
      if (res.ok) {
        fetchPreferences();
      }
    } catch (e) {
      console.error('Failed to reinforce preference', e);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Tier 3: Memory Summary Cards */}
      <div className="panel">
        <div className="panel-header">
          <div className="panel-title">
            <span className="panel-title-icon">📊</span>
            <h2>Memory Layer Capacities</h2>
          </div>
        </div>
        <div className="metrics-grid" style={{ marginTop: '12px' }}>
          <div style={{ background: 'var(--bg-glass)', padding: '16px', borderRadius: 'var(--radius-sm)' }}>
            <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>EPISODIC EVENTS</div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: '#fff', fontFamily: 'JetBrains Mono, monospace' }}>
              {cognitiveSnapshot?.tier_3_memory?.episodic_node_total ?? 48391}
            </div>
          </div>
          <div style={{ background: 'var(--bg-glass)', padding: '16px', borderRadius: 'var(--radius-sm)' }}>
            <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>SEMANTIC FACTS</div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: '#fff', fontFamily: 'JetBrains Mono, monospace' }}>
              {cognitiveSnapshot?.tier_3_memory?.semantic_vector_total ?? 12505}
            </div>
          </div>
          <div style={{ background: 'var(--bg-glass)', padding: '16px', borderRadius: 'var(--radius-sm)' }}>
            <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>RELATIONSHIPS</div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: '#fff', fontFamily: 'JetBrains Mono, monospace' }}>
              {cognitiveSnapshot?.tier_3_memory?.relationship_chapter_total ?? 286}
            </div>
          </div>
          <div style={{ background: 'var(--bg-glass)', padding: '16px', borderRadius: 'var(--radius-sm)' }}>
            <div style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>PREFERENCES RECORDED</div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: '#fff', fontFamily: 'JetBrains Mono, monospace' }}>
              {preferences.length}
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
        {/* Memory Search Panel */}
        <div className="panel" style={{ flex: '1 1 400px' }}>
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">🔍</span>
              <h2>Associative Memory Query</h2>
            </div>
          </div>
          <form onSubmit={handleSearch} style={{ display: 'flex', gap: '10px', marginTop: '12px' }}>
            <input
              type="text"
              placeholder="Query episodic or semantic memory layers..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                flex: 1,
                padding: '10px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-xs)',
                color: '#fff',
                fontSize: '13px'
              }}
            />
            <button
              type="submit"
              style={{
                padding: '10px 20px',
                background: 'var(--accent-blue)',
                border: 'none',
                borderRadius: 'var(--radius-xs)',
                color: '#fff',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              {searching ? 'Querying...' : 'Search'}
            </button>
          </form>

          <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {searchResults.length > 0 ? (
              searchResults.map((res, i) => (
                <div key={i} style={{ background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-secondary)' }}>
                    <span>ID: {res.id || 'N/A'}</span>
                    <span>Recall Score: {res.recall_score?.toFixed(3) || '1.0'}</span>
                  </div>
                  <div style={{ color: '#fff', fontSize: '13px', marginTop: '6px' }}>{res.text || res.content}</div>
                </div>
              ))
            ) : (
              searchQuery && !searching && (
                <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px', fontStyle: 'italic' }}>
                  No records returned.
                </div>
              )
            )}
          </div>
        </div>

        {/* User Preference Reinforcement */}
        <div className="panel" style={{ flex: '1 1 400px' }}>
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">⚙️</span>
              <h2>User Preference Manager</h2>
            </div>
          </div>

          <form onSubmit={handleCreatePreference} style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '12px' }}>
            <div style={{ display: 'flex', gap: '10px' }}>
              <input
                type="text"
                placeholder="Key (e.g. editor)"
                value={prefKey}
                onChange={(e) => setPrefKey(e.target.value)}
                style={{
                  flex: 1,
                  padding: '8px',
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-xs)',
                  color: '#fff',
                  fontSize: '12px'
                }}
              />
              <input
                type="text"
                placeholder="Value (e.g. vscode)"
                value={prefVal}
                onChange={(e) => setPrefVal(e.target.value)}
                style={{
                  flex: 1,
                  padding: '8px',
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-xs)',
                  color: '#fff',
                  fontSize: '12px'
                }}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                Initial Confidence: {prefConf.toFixed(2)}
                <input
                  type="range"
                  min="0.1"
                  max="1.0"
                  step="0.05"
                  value={prefConf}
                  onChange={(e) => setPrefConf(parseFloat(e.target.value))}
                  style={{ marginLeft: '10px', verticalAlign: 'middle' }}
                />
              </label>
              <button
                type="submit"
                style={{
                  padding: '8px 16px',
                  background: 'var(--accent-purple)',
                  border: 'none',
                  borderRadius: 'var(--radius-xs)',
                  color: '#fff',
                  fontWeight: 600,
                  fontSize: '11px',
                  cursor: 'pointer'
                }}
              >
                Set Preference
              </button>
            </div>
          </form>

          <table className="data-table" style={{ marginTop: '16px' }}>
            <thead>
              <tr>
                <th>Preference Key</th>
                <th>Preference Value</th>
                <th>Confidence</th>
                <th>Count</th>
                <th>Reinforce</th>
              </tr>
            </thead>
            <tbody>
              {preferences.length > 0 ? (
                preferences.map((p) => (
                  <tr key={p.pref_key}>
                    <td style={{ fontWeight: 'bold', color: '#fff' }}>{p.pref_key}</td>
                    <td>{JSON.stringify(p.pref_value)}</td>
                    <td style={{ fontFamily: 'monospace', color: p.confidence >= 0.6 ? 'var(--ok)' : 'var(--warn)' }}>
                      {p.confidence.toFixed(2)}
                    </td>
                    <td>{p.evidence_count}</td>
                    <td>
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <button
                          onClick={() => handleReinforce(p.pref_key, true)}
                          style={{
                            background: 'rgba(16, 185, 129, 0.2)',
                            color: 'var(--ok)',
                            border: '1px solid rgba(16, 185, 129, 0.4)',
                            borderRadius: '3px',
                            cursor: 'pointer',
                            padding: '2px 6px',
                            fontSize: '10px'
                          }}
                        >
                          👍
                        </button>
                        <button
                          onClick={() => handleReinforce(p.pref_key, false)}
                          style={{
                            background: 'rgba(239, 68, 68, 0.2)',
                            color: 'var(--critical)',
                            border: '1px solid rgba(239, 68, 68, 0.4)',
                            borderRadius: '3px',
                            cursor: 'pointer',
                            padding: '2px 6px',
                            fontSize: '10px'
                          }}
                        >
                          👎
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                    No preferences recorded.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
