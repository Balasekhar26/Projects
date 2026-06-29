import React, { useState } from 'react';

interface LedgerEvent {
  event_id: string;
  parent_event_id?: string | null;
  correlation_id: string;
  event_type: string;
  source_component: string;
  payload_json: string;
  timestamp: number;
}

interface LedgerPanelProps {
  ledgerEvents: LedgerEvent[];
  selectedLedgerEventId: string | null;
  onSelectEvent: (eventId: string | null) => void;
  ancestors: LedgerEvent[];
  descendants: LedgerEvent[];
  API_BASE: string;
}

export const LedgerPanel: React.FC<LedgerPanelProps> = ({
  ledgerEvents,
  selectedLedgerEventId,
  onSelectEvent,
  ancestors,
  descendants,
  API_BASE
}) => {
  const [filterType, setFilterType] = useState('');
  const [filterCorr, setFilterCorr] = useState('');
  const [replaying, setReplaying] = useState<string | null>(null);

  const selectedEvent = ledgerEvents.find(e => e.event_id === selectedLedgerEventId) || null;

  const filteredEvents = ledgerEvents.filter(e => {
    if (filterType && !e.event_type.toLowerCase().includes(filterType.toLowerCase())) return false;
    if (filterCorr && !e.correlation_id.toLowerCase().includes(filterCorr.toLowerCase())) return false;
    return true;
  });

  const handleReplay = async (eventId: string) => {
    setReplaying(eventId);
    try {
      const res = await fetch(`${API_BASE}/telemetry/replay/${eventId}`, {
        method: 'POST'
      });
      if (res.ok) {
        alert('Transaction replayed successfully!');
      } else {
        const err = await res.json();
        alert(`Replay failed: ${err.detail || 'Unknown error'}`);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setReplaying(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Search and Filters */}
      <div className="panel" style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', alignItems: 'center' }}>
        <h2 style={{ fontSize: '14px', color: '#fff', marginRight: 'auto' }}>📜 System Execution Ledger & Telemetry</h2>
        <div style={{ display: 'flex', gap: '10px' }}>
          <input
            type="text"
            placeholder="Filter by Event Type..."
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            style={{
              padding: '6px 12px',
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-xs)',
              color: '#fff',
              fontSize: '12px'
            }}
          />
          <input
            type="text"
            placeholder="Filter by Correlation ID..."
            value={filterCorr}
            onChange={(e) => setFilterCorr(e.target.value)}
            style={{
              padding: '6px 12px',
              background: 'rgba(255,255,255,0.03)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-xs)',
              color: '#fff',
              fontSize: '12px'
            }}
          />
        </div>
      </div>

      <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap' }}>
        {/* Ledger Event List */}
        <div className="panel" style={{ flex: '2 1 600px', maxHeight: '600px', overflowY: 'auto' }}>
          <div className="panel-header">
            <div className="panel-title">
              <span className="panel-title-icon">📊</span>
              <h2>Transaction History</h2>
            </div>
          </div>
          <table className="data-table" style={{ marginTop: '12px' }}>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Event Type</th>
                <th>Source</th>
                <th>Correlation ID</th>
                <th>Replay</th>
              </tr>
            </thead>
            <tbody>
              {filteredEvents.length > 0 ? (
                filteredEvents.map((event) => {
                  const isSelected = selectedLedgerEventId === event.event_id;
                  return (
                    <tr
                      key={event.event_id}
                      onClick={() => onSelectEvent(event.event_id)}
                      style={{
                        cursor: 'pointer',
                        background: isSelected ? 'rgba(20, 184, 166, 0.1)' : undefined,
                        borderLeft: isSelected ? '3px solid #14b8a6' : undefined
                      }}
                    >
                      <td style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                        {new Date(event.timestamp * 1000).toLocaleTimeString()}
                      </td>
                      <td style={{ fontWeight: '600', color: '#fff' }}>{event.event_type}</td>
                      <td style={{ fontSize: '12px' }}>{event.source_component}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: '11px', color: '#a78bfa' }}>
                        {event.correlation_id.substring(0, 8)}...
                      </td>
                      <td>
                        <button
                          disabled={replaying === event.event_id}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleReplay(event.event_id);
                          }}
                          style={{
                            background: 'rgba(20, 184, 166, 0.2)',
                            color: '#14b8a6',
                            border: '1px solid rgba(20, 184, 166, 0.4)',
                            borderRadius: '3px',
                            cursor: 'pointer',
                            padding: '2px 8px',
                            fontSize: '10px'
                          }}
                        >
                          {replaying === event.event_id ? 'Replaying...' : 'Replay'}
                        </button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', color: 'var(--text-muted)', fontStyle: 'italic', padding: '20px' }}>
                    No matching ledger events recorded.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Selected Event Trace Details */}
        <div className="panel" style={{ flex: '1 1 350px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {selectedEvent ? (
            <>
              <div>
                <h3 style={{ fontSize: '12px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                  Event Information
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', background: 'var(--bg-glass)', padding: '12px', borderRadius: 'var(--radius-xs)', border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: '11px' }}><span style={{ color: 'var(--text-secondary)' }}>ID:</span> <strong style={{ color: '#fff', wordBreak: 'break-all' }}>{selectedEvent.event_id}</strong></div>
                  <div style={{ fontSize: '11px' }}><span style={{ color: 'var(--text-secondary)' }}>Correlation ID:</span> <strong style={{ color: '#a78bfa', wordBreak: 'break-all' }}>{selectedEvent.correlation_id}</strong></div>
                  <div style={{ fontSize: '11px' }}><span style={{ color: 'var(--text-secondary)' }}>Parent ID:</span> <span style={{ color: 'var(--text-muted)', wordBreak: 'break-all' }}>{selectedEvent.parent_event_id || 'None'}</span></div>
                  <div style={{ fontSize: '11px' }}><span style={{ color: 'var(--text-secondary)' }}>Source:</span> <strong style={{ color: '#fff' }}>{selectedEvent.source_component}</strong></div>
                </div>
              </div>

              <div>
                <h3 style={{ fontSize: '12px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                  Payload Details
                </h3>
                <pre style={{
                  margin: 0,
                  padding: '12px',
                  background: 'rgba(0,0,0,0.2)',
                  borderRadius: 'var(--radius-xs)',
                  border: '1px solid var(--border)',
                  color: 'var(--ok)',
                  fontSize: '11px',
                  overflowX: 'auto',
                  maxHeight: '200px'
                }}>
                  {JSON.stringify(JSON.parse(selectedEvent.payload_json), null, 2)}
                </pre>
              </div>

              <div>
                <h3 style={{ fontSize: '12px', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                  Trace DAG Relations
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  {ancestors.length > 0 && (
                    <div>
                      <div style={{ fontSize: '10px', color: 'var(--text-secondary)', marginBottom: '4px' }}>Ancestors (Parents)</div>
                      {ancestors.map(a => (
                        <div key={a.event_id} style={{ fontSize: '11px', padding: '6px', background: 'rgba(255,255,255,0.02)', borderRadius: '3px', border: '1px dashed rgba(255,255,255,0.1)' }}>
                          ● {a.event_type} ({a.source_component})
                        </div>
                      ))}
                    </div>
                  )}

                  {descendants.length > 0 && (
                    <div style={{ marginTop: '8px' }}>
                      <div style={{ fontSize: '10px', color: 'var(--text-secondary)', marginBottom: '4px' }}>Descendants (Children)</div>
                      {descendants.map(d => (
                        <div key={d.event_id} style={{ fontSize: '11px', padding: '6px', background: 'rgba(255,255,255,0.02)', borderRadius: '3px', border: '1px dashed rgba(255,255,255,0.1)' }}>
                          ● {d.event_type} ({d.source_component})
                        </div>
                      ))}
                    </div>
                  )}

                  {ancestors.length === 0 && descendants.length === 0 && (
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                      No direct graph relations in current trace window.
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div style={{ display: 'flex', flex: 1, alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontStyle: 'italic', fontSize: '13px', textAlign: 'center' }}>
              Select a ledger transaction to inspect its correlation tracking and payload context.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
