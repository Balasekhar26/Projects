#!/usr/bin/env python3
import sys
import time
import json
from pathlib import Path
from datetime import datetime

# Add workspace to path
WORKSPACE_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.progress import ProgressBar

from backend.core.governor import DecisionArbiter, SystemPolicyMode, GovernorAction

class GovernorDashboard:
    """
    RG-Dash: Live Rich-based terminal UI displaying governor telemetries,
    Arbiter decisions, and versioned evaluation suite scorecards.
    """
    
    def __init__(self):
        self.arbiter = DecisionArbiter()
        self.layout = Layout()
        self._init_layout()

    def _init_layout(self):
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )
        self.layout["main"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1)
        )
        self.layout["left"].split(
            Layout(name="status", ratio=1),
            Layout(name="metrics", ratio=2)
        )
        self.layout["right"].split(
            Layout(name="system", ratio=1),
            Layout(name="evaluations", ratio=1)
        )

    def generate_header(self) -> Panel:
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        title = Text.assemble(
            (" ⚡ ", "bold yellow"),
            ("KATTAPPA COGNITIVE OS — RESOURCE GOVERNOR ", "bold white"),
            (" ⚡", "bold yellow")
        )
        return Panel(
            Align.center(Text.assemble(title, (f" | Live Telemetry: {time_str}", "dim white"))),
            style="bold cyan border",
            padding=(0, 1)
        )

    def generate_status(self, dec: dict) -> Panel:
        policy = dec["active_policy"]
        action = dec["recommended_action"]
        risk = dec["max_risk_score"]
        worst = dec["worst_governor"]
        reason = dec["reason"]
        
        # Color mapping for policy mode
        policy_color = {
            SystemPolicyMode.MAXIMUM: "bold red",
            SystemPolicyMode.PERFORMANCE: "bold green",
            SystemPolicyMode.BALANCED: "bold yellow",
            SystemPolicyMode.ECO: "bold orange3"
        }.get(policy, "bold white")
        
        action_color = {
            GovernorAction.NONE: "bold green",
            GovernorAction.ECO: "bold yellow",
            GovernorAction.PAUSE: "bold red",
            GovernorAction.SHUTDOWN: "bold reverse red"
        }.get(action, "bold white")

        table = Table.minimal_grid(num_rows=4)
        table.add_column("Key", style="bold dim white", width=20)
        table.add_column("Value", style="bold white")
        
        table.add_row("Active Policy Profile:", Text(policy.upper(), style=policy_color))
        table.add_row("Arbiter Decision:", Text(action.upper(), style=action_color))
        table.add_row("Worst Governor:", Text(str(worst).upper(), style="bold magenta"))
        table.add_row("Arbiter Reason:", Text(reason, style="dim italic white"))

        # Risk progress bar
        risk_color = "green"
        if risk > 0.8:
            risk_color = "red"
        elif risk > 0.5:
            risk_color = "yellow"

        bar = ProgressBar(total=1.0, completed=risk, width=30, style=f"bold {risk_color}")
        
        panel_content = Layout()
        panel_content.split_row(
            Layout(table, ratio=2),
            Layout(Align.center(Panel(bar, title=f"Risk Score: {risk:.2f}", border_style=risk_color)), ratio=1)
        )

        return Panel(
            panel_content,
            title="Arbiter Decision Status",
            border_style="green" if action == GovernorAction.NONE else "yellow" if action == GovernorAction.ECO else "red"
        )

    def generate_metrics_table(self, dec: dict) -> Panel:
        details = dec["governor_details"]
        table = Table(title="Subsystem Sensor Details", show_header=True, header_style="bold cyan")
        table.add_column("Governor", style="bold white")
        table.add_column("Capacity", justify="right")
        table.add_column("Risk Score", justify="right")
        table.add_column("Priority", justify="right")
        table.add_column("Confidence", justify="right")
        table.add_column("Action", justify="center")

        for name, res in details.items():
            cap = res["available_capacity"]
            risk = res["risk_score"]
            pri = res["priority"]
            conf = res.get("confidence", 1.0)
            act = res["recommended_action"]
            
            act_style = "green" if act == GovernorAction.NONE else "yellow" if act == GovernorAction.ECO else "red"
            risk_style = "red" if risk > 0.8 else "yellow" if risk > 0.5 else "white"

            table.add_row(
                name.upper(),
                f"{cap:.1f}%",
                Text(f"{risk:.2f}", style=risk_style),
                str(pri),
                f"{conf:.2f}",
                Text(act.upper(), style=act_style)
            )

        return Panel(table, border_style="cyan")

    def generate_system_raw(self, dec: dict) -> Panel:
        details = dec["governor_details"]
        
        # CPU
        cpu_metrics = details.get("cpu", {}).get("metrics", {})
        cpu_val = cpu_metrics.get("cpu_percent", 0.0)
        cpu_30s = cpu_metrics.get("cpu_30s_avg", 0.0)
        
        # GPU
        gpu_metrics = details.get("gpu", {}).get("metrics", {})
        vram_alloc = gpu_metrics.get("allocated_gb", 0.0)
        vram_max = gpu_metrics.get("recommended_max_gb", 0.0)
        
        # Memory
        mem_metrics = details.get("memory", {}).get("metrics", {})
        ram_pct = mem_metrics.get("ram_percent", 0.0)
        swap = mem_metrics.get("swap_used_gb", 0.0)
        pageouts = mem_metrics.get("smoothed_pageouts_rate", 0.0)
        
        # Thermal
        therm_metrics = details.get("thermal", {}).get("metrics", {})
        temp = therm_metrics.get("temperature_c", 0.0)
        
        # Battery
        bat_metrics = details.get("battery", {}).get("metrics", {})
        bat_pct = bat_metrics.get("percent", 100.0)
        plugged = bat_metrics.get("power_plugged", True)

        grid = Table.minimal_grid(num_rows=5)
        grid.add_column("Resource", style="bold cyan", width=15)
        grid.add_column("Telemetry Details", style="bold white")

        grid.add_row("CPU Load:", f"Instant: {cpu_val:.1f}% | 30s Smoothed: {cpu_30s:.1f}%")
        grid.add_row("GPU (MPS):", f"VRAM Allocated: {vram_alloc:.2f} GB / {vram_max:.2f} GB")
        grid.add_row("RAM & Swap:", f"Physical: {ram_pct:.1f}% | Swap: {swap:.2f} GB | Pageouts: {pageouts:.2f}/s")
        grid.add_row("Thermal State:", f"Chip Temperature: {temp:.1f}°C")
        grid.add_row("Battery Power:", f"Charge: {bat_pct:.1f}% | Plugged: {'Yes (AC)' if plugged else 'No (Discharging)'}")

        return Panel(grid, title="Raw System Telemetry", border_style="magenta")

    def generate_eval_history(self) -> Panel:
        table = Table(title="Evaluation Scorecards", show_header=True, header_style="bold yellow")
        table.add_column("Suite Version", style="bold white")
        table.add_column("Telugu", justify="right")
        table.add_column("Reasoning", justify="right")
        table.add_column("Memory", justify="right")
        table.add_column("Coding", justify="right")
        table.add_column("Tool Selection", justify="right")
        
        # Scan for existing suite reports
        report_dir = WORKSPACE_ROOT / "kattappa/kattappa_data_engine/reports"
        suites_found = False
        
        if report_dir.exists():
            for filepath in sorted(report_dir.glob("evaluation_suite_*.json")):
                if "current" in filepath.name:
                    continue
                try:
                    version = filepath.name.replace("evaluation_suite_", "").replace(".json", "")
                    with open(filepath, "r") as f:
                        data = json.load(f)
                    metrics = data.get("metrics", {})
                    table.add_row(
                        version.upper(),
                        f"{metrics.get('telugu', 0.0)*100:.1f}%",
                        f"{metrics.get('reasoning', 0.0)*100:.1f}%",
                        f"{metrics.get('memory', 0.0)*100:.1f}%",
                        f"{metrics.get('engineering', 0.0)*100:.1f}%",
                        f"{metrics.get('tool_selection', 0.0)*100:.1f}%"
                    )
                    suites_found = True
                except Exception:
                    pass
                    
        if not suites_found:
            table.add_row("NO REPORTS", "-", "-", "-", "-", "-")

        return Panel(table, border_style="yellow")

    def generate_footer(self) -> Panel:
        return Panel(
            Align.center(Text("Press Ctrl+C to terminate dashboard monitoring loop.", style="bold dim red")),
            style="dim white",
            padding=(0, 1)
        )

    def draw(self):
        dec = self.arbiter.assess_system()
        
        self.layout["header"].update(self.generate_header())
        self.layout["status"].update(self.generate_status(dec))
        self.layout["metrics"].update(self.generate_metrics_table(dec))
        self.layout["system"].update(self.generate_system_raw(dec))
        self.layout["evaluations"].update(self.generate_eval_history())
        self.layout["footer"].update(self.generate_footer())
        
        return self.layout

def main():
    dash = GovernorDashboard()
    try:
        with Live(dash.draw(), refresh_per_second=1, screen=True) as live:
            while True:
                time.sleep(1.0)
                live.update(dash.draw())
    except KeyboardInterrupt:
        print("\nRG-Dash terminated cleanly.")

if __name__ == "__main__":
    main()
