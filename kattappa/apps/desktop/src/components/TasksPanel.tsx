import type { LongTask, ResumeResult } from "../types";

type TasksPanelProps = {
  longTasks: LongTask[];
  taskDraft: { title: string; goal: string; priority: string };
  resumeResult: ResumeResult | null;
  onTaskDraftChange: (draft: { title: string; goal: string; priority: string }) => void;
  onCreateLongTask: () => void;
  onRefreshLongTasks: () => void;
  onContinueLongTask: (task: LongTask) => void;
  onPlanLongTaskResume: (task: LongTask) => void;
  onUpdateLongTask: (taskId: string, update: Partial<Pick<LongTask, "status" | "progress" | "next_step">>) => void;
};

export function TasksPanel({
  longTasks,
  taskDraft,
  resumeResult,
  onTaskDraftChange,
  onCreateLongTask,
  onRefreshLongTasks,
  onContinueLongTask,
  onPlanLongTaskResume,
  onUpdateLongTask,
}: TasksPanelProps) {
  return (
    <section className="panelView">
      <h2>Long Tasks</h2>
      <p>Use this for work that should survive restarts: builds, research, debugging, project upgrades, and anything you want Kattappa AI OS to resume later.</p>
      <div className="taskComposer">
        <input
          value={taskDraft.title}
          onChange={(event) => onTaskDraftChange({ ...taskDraft, title: event.target.value })}
          placeholder="Task title"
        />
        <textarea
          value={taskDraft.goal}
          onChange={(event) => onTaskDraftChange({ ...taskDraft, goal: event.target.value })}
          placeholder="Goal and important details"
          rows={3}
        />
        <div className="taskControls">
          <select
            value={taskDraft.priority}
            onChange={(event) => onTaskDraftChange({ ...taskDraft, priority: event.target.value })}
          >
            <option value="normal">Normal</option>
            <option value="high">High</option>
            <option value="low">Low</option>
          </select>
          <button onClick={onCreateLongTask}>Save Long Task</button>
          <button onClick={onRefreshLongTasks}>Refresh</button>
        </div>
      </div>
      <div className="taskList">
        {longTasks.length ? longTasks.map((task) => (
          <article key={task.id} className={`taskItem ${task.status}`}>
            <header>
              <strong>{task.title}</strong>
              <span>{task.status} / {task.priority}</span>
            </header>
            <p>{task.goal}</p>
            <dl>
              <dt>Progress</dt>
              <dd>{task.progress || "Not recorded yet"}</dd>
              <dt>Next</dt>
              <dd>{task.next_step || "Ask for the next approved step"}</dd>
            </dl>
            <div className="taskActions">
              <button onClick={() => onContinueLongTask(task)}>Continue</button>
              <button onClick={() => onPlanLongTaskResume(task)}>Plan Resume</button>
              {task.status !== "done" && (
                <button onClick={() => onUpdateLongTask(task.id, { status: "done", progress: task.progress || "Completed from the Tasks tab." })}>Done</button>
              )}
              {task.status === "active" ? (
                <button onClick={() => onUpdateLongTask(task.id, { status: "paused" })}>Pause</button>
              ) : (
                <button onClick={() => onUpdateLongTask(task.id, { status: "active" })}>Resume</button>
              )}
            </div>
          </article>
        )) : <p>No long tasks saved yet.</p>}
      </div>
      {resumeResult && (
        <div className="resumePanel">
          <h3>Resume Plan</h3>
          <p>{resumeResult.task.title}</p>
          <ol>
            {resumeResult.next_steps.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ol>
        </div>
      )}
    </section>
  );
}
