import random
from pipeline.synthetic.generator_base import BaseGenerator

class PlanningGenerator(BaseGenerator):
    def __init__(self):
        super().__init__("planning")
        self.domains = [
            "Embedded Systems", "RF Engineering", "Database Cluster", "Cloud Infrastructure", 
            "API Gateway", "Hardware Test Automation", "Product Safety", "Firmware OTA"
        ]
        self.scenarios = [
            {
                "task": "Migrating a live {db_name} database to a new instance with zero downtime",
                "steps": [
                    "Perform baseline performance and capacity audits on the source database.",
                    "Set up the new database instance and initiate raw logical replication.",
                    "Configure dual-write logic in the application layer (write to both instances, read from source).",
                    "Verify replication log alignment and check for zero datadiff drift.",
                    "Update DNS and cutover read paths to the new instance.",
                    "Maintain the old instance as a fallback replica for 48 hours before teardown."
                ],
                "risks": [
                    "Replication lag under heavy write loads causing dirty reads.",
                    "DNS propagation delays causing some client write operations to hit the old instance post-cutover."
                ],
                "mitigations": [
                    "Enforce strict row-level version matching and sequential conflict resolution in dual-write paths.",
                    "Use low TTL values on DNS (e.g. 60 seconds) and run application-level proxy routers during cutover."
                ],
                "skills": ["database_migration", "zero_downtime", "resilience_planning"]
            },
            {
                "task": "Designing a reliable over-the-air (FOTA) firmware update plan for {device_count} IoT devices",
                "steps": [
                    "Build and cryptographically sign the new binary with asymmetric keys.",
                    "Verify the binary signature and bootloader rollback recovery inside a hardware loop simulator.",
                    "Staged rollouts: deploy to a canary group (1% of devices) and monitor crash logs for 24 hours.",
                    "Expand rollout in waves (10%, 25%, 50%, 100%) checking watchdog timer flags.",
                    "Configure dynamic fallback boot routines if the new firmware fails to boot twice."
                ],
                "risks": [
                    "Sudden power loss during flash write operations leading to bricked devices.",
                    "Weak RF link budget leading to truncated download packets."
                ],
                "mitigations": [
                    "Use A/B partition layout: flash the inactive partition first, verify checksum, and switch boot pointers.",
                    "Enforce block-by-block MD5 hash checks and resume download support in the bootloader."
                ],
                "skills": ["firmware_ota", "fail_safe_design", "embedded_systems"]
            },
            {
                "task": "Deploying a high-throughput API Rate Limiter across {server_count} distributed nodes",
                "steps": [
                    "Audit and map endpoint resource thresholds (e.g., read vs write limits).",
                    "Set up a centralized Redis cluster to hold client token bucket states.",
                    "Implement a local in-memory token bucket fallback on each server node.",
                    "Write an atomic Lua script for Redis token operations to eliminate write race conditions.",
                    "Deploy fail-open routing policies so rate-limiter timeouts don't block requests."
                ],
                "risks": [
                    "Redis cluster connection timeout creating 100ms+ API tail latency spikes.",
                    "IP spoofing or proxy routing bypassing the rate-limiting keys."
                ],
                "mitigations": [
                    "Implement circuit breakers that switch to local in-memory counting if Redis connection latency exceeds 10ms.",
                    "Track clients using client-specific HMAC tokens rather than raw IP addresses."
                ],
                "skills": ["api_design", "distributed_systems", "rate_limiting"]
            },
            {
                "task": "Designing an automated hardware testing roadmap for an {rf_type} telemetry module",
                "steps": [
                    "Configure RF test chambers with calibrated spectrum analyzers and loop couplers.",
                    "Write automated test scripts in Python to sweep transmit power and receiver sensitivity.",
                    "Measure packet error rate (PER) across temperature variations (-20C to 80C) in a thermal chamber.",
                    "Run stress testing for 48 hours to profile CPU cache alignment and SPI bus throughput.",
                    "Log RSSI values and transmit current draw to verify link budget targets."
                ],
                "risks": [
                    "Impedance mismatch (VSWR > 2.0) causing thermal damage to the RF power amplifier.",
                    "Electromagnetic interference (EMI) from the digital power rails corrupting telemetry signals."
                ],
                "mitigations": [
                    "Implement directional couplers with automated shutdown logic if high reflected power is detected.",
                    "Enforce proper PCB shield isolation and trace grounding before running high-power loops."
                ],
                "skills": ["rf_systems", "test_automation", "hardware_validation"]
            }
        ]

    def generate_plan(self, idx, seed_val):
        self.set_seed(seed_val)
        
        # Select base scenario
        scenario_template = self.scenarios[idx % len(self.scenarios)]
        
        # Populate template variables dynamically
        db_names = ["PostgreSQL", "Cassandra", "MySQL", "MongoDB", "DynamoDB"]
        rf_types = ["SPI-based LoRa", "UART-based Zigbee", "BLE 5.2 Sensor", "WiFi Telemetry"]
        
        db_name = random.choice(db_names)
        device_count = random.choice([5000, 10000, 50000, 100000])
        server_count = random.choice([10, 20, 50, 100])
        rf_type = random.choice(rf_types)
        
        task_title = scenario_template["task"].format(
            db_name=db_name, device_count=device_count, 
            server_count=server_count, rf_type=rf_type
        )
        
        # Format the planning roadmap
        question = f"Planning Request #{idx}: Create a comprehensive step-by-step engineering plan for: {task_title}. Highlight key risks, mitigations, and execution phases."
        
        solution = (
            f"Step 1: Parse requirements for '{task_title}'.\n"
            f"Step 2: Build a structured 5-stage deployment plan.\n"
            f"Step 3: Define failure modes and safety mitigations."
        )
        
        # Build answer
        answer = f"### Project Objective\n{task_title}.\n\n"
        answer += "### Execution Milestones\n"
        for j, step in enumerate(scenario_template["steps"]):
            answer += f"{j+1}. **Phase {j+1}**: {step}\n"
            
        answer += "\n### Risk Analysis & Mitigations\n"
        for j, (risk, mit) in enumerate(zip(scenario_template["risks"], scenario_template["mitigations"])):
            answer += f"- **Risk {j+1}**: {risk}\n"
            answer += f"  - *Mitigation*: {mit}\n"
            
        difficulty = "hard" if idx % 3 == 0 else "medium"
        
        return {
            "id": self.generate_id(idx),
            "category": "planning",
            "difficulty": difficulty,
            "language": "english",
            "question": question,
            "solution_outline": solution,
            "answer": answer,
            "source": "synthetic",
            "generator": "factory",
            "quality_score": 0.98,
            "verified": True,
            "skills": scenario_template["skills"],
            "estimated_tokens": self.estimate_tokens(question, solution, answer)
        }

    def generate_batch(self, count):
        return [self.generate_plan(i + 1, 2000 + i) for i in range(count)]
