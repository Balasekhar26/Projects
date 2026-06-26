import random
from pipeline.synthetic.generator_base import BaseGenerator

class ToolGenerator(BaseGenerator):
    def __init__(self):
        super().__init__("tool")
        self.log_folders = ["/var/log/nginx", "/home/user/reports", "/opt/tomcat/logs", "/var/log/syslog"]
        self.databases = ["users_prod", "inventory_db", "telemetry_records", "billing_replica"]
        self.admins = ["admin@kattappa.io", "secops@kattappa.io", "hardware_lead@kattappa.io"]

    def generate_log_cleanup_trace(self, idx, seed_val):
        self.set_seed(seed_val)
        folder = random.choice(self.log_folders)
        keyword = random.choice(["FATAL", "ERROR", "CRITICAL", "OOM"])
        log_file = f"service_{random.randint(100, 999)}_error.log"
        
        question = f"Tool Task #{idx}: Locate any log files under '{folder}' containing the keyword '{keyword}', extract the matching lines, and delete the log file if it exceeds 10MB."
        
        solution = (
            f"Step 1: Call filesystem.list_files for folder '{folder}'.\n"
            f"Step 2: Check matching files for keyword '{keyword}' and file size.\n"
            f"Step 3: Call filesystem.delete on log files exceeding size limits."
        )
        
        answer = (
            f"**Action 1**: List files in folder.\n"
            f"`tool_call: filesystem.list_files(path=\"{folder}\", pattern=\"*.log\")`\n"
            f"**Observation 1**:\n"
            f"`[\n  {{\"name\": \"{log_file}\", \"size_bytes\": 12582912}}\n]`\n\n" # 12MB
            f"**Action 2**: Grep keyword in the log file.\n"
            f"`tool_call: filesystem.grep(path=\"{folder}/{log_file}\", query=\"{keyword}\")`\n"
            f"**Observation 2**:\n"
            f"`[\n  \"L104: [14:02:11] {keyword} Connection closed by peer\"\n]`\n\n"
            f"**Action 3**: File size is 12.5MB (exceeds 10MB target limit). Delete file.\n"
            f"`tool_call: filesystem.delete(path=\"{folder}/{log_file}\")`\n"
            f"**Observation 3**:\n"
            f"`{{\"status\": \"success\", \"deleted_count\": 1}}`\n\n"
            f"**Response**: Found 1 log file ({log_file}) exceeding 10MB containing '{keyword}'. "
            f"Extracted matching line \"L104: [14:02:11] {keyword} Connection closed by peer\" and deleted it successfully."
        )
        
        return {
            "id": self.generate_id(idx),
            "category": "tool_usage",
            "difficulty": "hard",
            "language": "english",
            "question": question,
            "solution_outline": solution,
            "answer": answer,
            "source": "synthetic",
            "generator": "factory",
            "quality_score": 0.98,
            "verified": True,
            "skills": ["tool_use", "filesystem_ops", "log_analysis"],
            "estimated_tokens": self.estimate_tokens(question, solution, answer)
        }

    def generate_dns_diag_trace(self, idx, seed_val):
        self.set_seed(seed_val)
        subdomain = random.choice(["api", "metrics", "db-replica", "sensor-node"])
        domain = f"{subdomain}.local"
        ip = f"192.168.1.{random.randint(10, 250)}"
        port = random.choice([80, 443, 8080])
        
        question = f"Tool Task #{idx}: Check the DNS address for '{domain}', verify if the server port {port} is reachable, and fetch the API status."
        
        solution = (
            f"Step 1: Resolve DNS address for domain '{domain}'.\n"
            f"Step 2: Execute ping/port test to check reachability on port {port}.\n"
            f"Step 3: Call network.http_get on status endpoint."
        )
        
        answer = (
            f"**Action 1**: Resolve hostname.\n"
            f"`tool_call: network.dns_resolve(hostname=\"{domain}\")`\n"
            f"**Observation 1**:\n"
            f"`{{\"status\": \"success\", \"ip\": \"{ip}\"}}`\n\n"
            f"**Action 2**: Test port connection.\n"
            f"`tool_call: network.port_check(ip=\"{ip}\", port={port})`\n"
            f"**Observation 2**:\n"
            f"`{{\"status\": \"reachable\", \"latency_ms\": 2.4}}`\n\n"
            f"**Action 3**: Query status endpoint.\n"
            f"`tool_call: network.http_get(url=\"https://{ip}:{port}/api/status\")`\n"
            f"**Observation 3**:\n"
            f"`{{\"status_code\": 200, \"body\": {{\"uptime\": 36000, \"version\": \"1.0.2\", \"db_connected\": true}}}}`\n\n"
            f"**Response**: DNS for '{domain}' resolved to {ip}. Port {port} is reachable with a latency of 2.4ms. "
            f"API is operational with uptime of 36000 seconds, running version 1.0.2."
        )
        
        return {
            "id": self.generate_id(idx),
            "category": "tool_usage",
            "difficulty": "medium",
            "language": "english",
            "question": question,
            "solution_outline": solution,
            "answer": answer,
            "source": "synthetic",
            "generator": "factory",
            "quality_score": 0.98,
            "verified": True,
            "skills": ["tool_use", "networking_diag", "dns_lookup"],
            "estimated_tokens": self.estimate_tokens(question, solution, answer)
        }

    def generate_db_backup_trace(self, idx, seed_val):
        self.set_seed(seed_val)
        db = random.choice(self.databases)
        admin = random.choice(self.admins)
        backup_file = f"backup_{db}_{random.randint(1000, 9999)}.sql"
        
        question = f"Tool Task #{idx}: Query the database '{db}' for user audit flags, generate a backup of the records, and notify the security lead at '{admin}'."
        
        solution = (
            f"Step 1: Execute db.query to retrieve flagged logs.\n"
            f"Step 2: Call database.dump to create local backup archive.\n"
            f"Step 3: Call notifications.send_email to notify '{admin}'."
        )
        
        answer = (
            f"**Action 1**: Query audit flags.\n"
            f"`tool_call: database.query(db=\"{db}\", sql=\"SELECT count(*) FROM audit_logs WHERE flagged = true\")`\n"
            f"**Observation 1**:\n"
            f"`{{\"count\": 124}}`\n\n"
            f"**Action 2**: Run backup dump.\n"
            f"`tool_call: database.dump(db=\"{db}\", tables=[\"audit_logs\"], output_file=\"{backup_file}\")`\n"
            f"**Observation 2**:\n"
            f"`{{\"status\": \"success\", \"filepath\": \"/tmp/{backup_file}\", \"size_bytes\": 45091}}`\n\n"
            f"**Action 3**: Send email notification.\n"
            f"`tool_call: notifications.send_email(recipient=\"{admin}\", subject=\"Security Audit Backup: {db}\", body=\"Audit count: 124. Saved to {backup_file}\")`\n"
            f"**Observation 3**:\n"
            f"`{{\"status\": \"sent\", \"message_id\": \"msg_78xyz89\"}}`\n\n"
            f"**Response**: Database '{db}' has 124 flagged audit logs. "
            f"Created SQL backup /tmp/{backup_file} (45KB) and sent an email report to the security lead at '{admin}'."
        )
        
        return {
            "id": self.generate_id(idx),
            "category": "tool_usage",
            "difficulty": "hard",
            "language": "english",
            "question": question,
            "solution_outline": solution,
            "answer": answer,
            "source": "synthetic",
            "generator": "factory",
            "quality_score": 0.98,
            "verified": True,
            "skills": ["tool_use", "database_ops", "notification_flow"],
            "estimated_tokens": self.estimate_tokens(question, solution, answer)
        }

    def generate_batch(self, count):
        batch = []
        for i in range(count):
            seed = 5000 + i
            choice = i % 3
            if choice == 0:
                batch.append(self.generate_log_cleanup_trace(i + 1, seed))
            elif choice == 1:
                batch.append(self.generate_dns_diag_trace(i + 1, seed))
            else:
                batch.append(self.generate_db_backup_trace(i + 1, seed))
        return batch
