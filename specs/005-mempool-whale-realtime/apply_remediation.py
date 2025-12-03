#!/usr/bin/env python3
"""
Automated Remediation Script for Mempool Whale Detection Specification
Applies critical security fixes and missing requirement coverage
Generated from Specification Analysis Report
"""

import os
import re
import shutil
from datetime import datetime
from pathlib import Path


class SpecificationRemediation:
    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self.backup_dir = (
            self.base_path / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        self.changes_log = []

    def backup_files(self):
        """Create backups of all files to be modified"""
        files_to_backup = ["tasks.md", "spec.md", "plan.md"]

        print(f"📁 Creating backup directory: {self.backup_dir}")
        self.backup_dir.mkdir(exist_ok=True)

        for file in files_to_backup:
            src = self.base_path / file
            if src.exists():
                dst = self.backup_dir / file
                shutil.copy2(src, dst)
                print(f"  ✅ Backed up {file}")

    def apply_tasks_security_edits(self):
        """Apply critical security task additions to tasks.md"""
        file_path = self.base_path / "tasks.md"

        with open(file_path, "r") as f:
            content = f.read()

        # Edit 1.1: Add authentication tasks after T018
        auth_tasks = """- [ ] T018 [P] [US1] Implement client connection management and broadcast logic
- [ ] T018a [US1] Implement JWT authentication for WebSocket server connections in scripts/auth/websocket_auth.py
- [ ] T018b [US1] Add token validation middleware to whale_alert_broadcaster.py"""

        content = content.replace(
            "- [ ] T018 [P] [US1] Implement client connection management and broadcast logic",
            auth_tasks,
        )
        self.changes_log.append("Added T018a, T018b: WebSocket authentication tasks")

        # Edit 1.2: Add dashboard authentication after T030
        dashboard_auth = """- [ ] T030 [US3] Implement WebSocket client in frontend/js/mempool_predictions.js
- [ ] T030a [US3] Add authentication token management to dashboard WebSocket client
- [ ] T030b [US3] Implement secure token storage and refresh logic in frontend"""

        content = content.replace(
            "- [ ] T030 [US3] Implement WebSocket client in frontend/js/mempool_predictions.js",
            dashboard_auth,
        )
        self.changes_log.append("Added T030a, T030b: Dashboard authentication tasks")

        # Edit 1.3: Update T036 with API authentication
        api_auth = """- [ ] T036 [P] [US3] Create REST API endpoints for historical queries in api/mempool_whale_endpoints.py
- [ ] T036a [US3] Implement API key authentication middleware for REST endpoints
- [ ] T036b [P] [US3] Add rate limiting per API key to prevent abuse"""

        content = content.replace(
            "- [ ] T036 [P] [US3] Create REST API endpoints for historical queries in api/mempool_whale_endpoints.py",
            api_auth,
        )
        self.changes_log.append("Added T036a, T036b: API authentication tasks")

        # Edit 2.1: Add operator alerting tasks after T042
        operator_alerts = """- [ ] T042 [US4] Create correlation statistics aggregation (daily/weekly/monthly)
- [ ] T042a [US4] Implement accuracy monitoring with configurable thresholds in scripts/accuracy_monitor.py
- [ ] T042b [US4] Add operator alerting when accuracy falls below 70% threshold
- [ ] T042c [P] [US4] Create webhook/email notifications for accuracy degradation alerts"""

        content = content.replace(
            "- [ ] T042 [US4] Create correlation statistics aggregation (daily/weekly/monthly)",
            operator_alerts,
        )
        self.changes_log.append("Added T042a, T042b, T042c: Operator alerting tasks")

        # Edit 3.1: Add webhook tasks after T055
        webhook_tasks = """- [ ] T055 [P] Add systemd service configuration for production deployment
- [ ] T056 Implement webhook notification system in scripts/webhook_notifier.py
- [ ] T057 Add webhook URL configuration and management interface
- [ ] T058 Implement webhook payload signing for security (HMAC-SHA256)
- [ ] T059 [P] Add webhook retry logic with exponential backoff
- [ ] T060 [P] Create webhook delivery status tracking and logging"""

        content = content.replace(
            "- [ ] T055 [P] Add systemd service configuration for production deployment",
            webhook_tasks,
        )
        self.changes_log.append("Added T056-T060: Webhook implementation tasks")

        # Update total task count
        content = re.sub(r"\*\*Total Tasks\*\*: \d+", "**Total Tasks**: 66", content)
        content = re.sub(
            r"\*\*Parallelizable\*\*: \d+ tasks marked with \[P\]",
            "**Parallelizable**: 35 tasks marked with [P]",
            content,
        )
        self.changes_log.append("Updated task counts: 66 total, 35 parallelizable")

        with open(file_path, "w") as f:
            f.write(content)

        print("✅ Applied security and feature tasks to tasks.md")

    def apply_spec_security_requirements(self):
        """Add security requirements and clarify edge cases in spec.md"""
        file_path = self.base_path / "spec.md"

        with open(file_path, "r") as f:
            lines = f.readlines()

        # Find FR-018 line number
        fr018_idx = None
        for i, line in enumerate(lines):
            if "FR-018" in line:
                fr018_idx = i
                break

        if fr018_idx:
            # Add new security requirements after FR-018
            new_requirements = [
                "- **FR-019**: System MUST implement authentication for all WebSocket connections using JWT tokens or API keys\n",
                "- **FR-020**: System MUST validate authentication tokens on every message and reject unauthorized connections\n",
                "- **FR-021**: System MUST implement rate limiting per authenticated client to prevent abuse\n",
            ]
            lines[fr018_idx + 1 : fr018_idx + 1] = new_requirements
            self.changes_log.append(
                "Added FR-019, FR-020, FR-021: Security requirements"
            )

        # Replace edge cases section with detailed version
        edge_start = None
        edge_end = None
        for i, line in enumerate(lines):
            if "### Edge Cases" in line:
                edge_start = i
            if edge_start and i > edge_start and line.startswith("## "):
                edge_end = i
                break

        if edge_start and edge_end:
            detailed_edge_cases = """### Edge Cases

- **RBF Transaction Replacement**: System updates the existing prediction with new parameters and flags it as "modified" while maintaining prediction ID continuity
- **Blockchain Reorganization**: When a confirmed transaction becomes unconfirmed due to reorg:
  - System reverts transaction status from "confirmed" to "pending"
  - Correlation statistics are recalculated excluding the reorged block
  - Dashboard displays reorg warning indicator
  - Predictions maintain original timestamp for accuracy tracking
- **Memory Pressure**: System drops low-fee transactions when memory reaches 400MB (80% of 500MB limit):
  - Transactions dropped in order of increasing fee rate (lowest first)
  - Minimum retention of top 100 highest-fee whale transactions
  - Memory status exposed via monitoring endpoint
- **Double-Spend Detection**: When conflicting transactions are detected:
  - Both transactions tracked with "conflict" flag
  - Higher fee transaction marked as likely winner
  - Dashboard shows conflict warning on affected predictions
  - Resolution tracked when one confirms
- **Fee Market Spike** (>5x increase in 10 minutes):
  - Urgency scores recalibrated using new fee percentiles
  - Historical predictions marked with "fee_spike" context flag
  - Confirmation time estimates adjusted dynamically
  - Operator alerted to review thresholds

"""
            lines[edge_start:edge_end] = [detailed_edge_cases]
            self.changes_log.append(
                "Expanded edge cases with detailed handling strategies"
            )

        # Consolidate FR-008 and FR-018
        for i, line in enumerate(lines):
            if "FR-008" in line:
                lines[i] = (
                    "- **FR-008**: System MUST maintain memory usage under 500MB limit by using streaming architecture, bounded collections, dropping low-fee transactions at 400MB threshold, maintaining minimum high-priority set, and exposing memory metrics\n"
                )
                self.changes_log.append(
                    "Consolidated FR-008 with memory management details"
                )
                break

        # Remove FR-018 (now consolidated into FR-008)
        lines = [
            line
            for line in lines
            if "FR-018" not in line or "memory pressure" not in line.lower()
        ]

        with open(file_path, "w") as f:
            f.writelines(lines)

        print(
            "✅ Applied security requirements and edge case clarifications to spec.md"
        )

    def apply_plan_structure_updates(self):
        """Update plan.md with new directory structure for auth modules"""
        file_path = self.base_path / "plan.md"

        with open(file_path, "r") as f:
            content = f.read()

        # Find the scripts/ section and enhance it
        old_structure = """scripts/
├── mempool_whale_monitor.py     # Main WebSocket client and monitoring service
├── whale_urgency_scorer.py      # Fee-based urgency calculation module
└── whale_alert_broadcaster.py   # Alert distribution via WebSocket/webhooks"""

        new_structure = """scripts/
├── mempool_whale_monitor.py     # Main WebSocket client and monitoring service
├── whale_urgency_scorer.py      # Fee-based urgency calculation module
├── whale_alert_broadcaster.py   # Alert distribution via WebSocket/webhooks
├── webhook_notifier.py           # Webhook notification system
├── accuracy_monitor.py           # Accuracy threshold monitoring
└── auth/
    └── websocket_auth.py         # JWT authentication for WebSocket connections"""

        content = content.replace(old_structure, new_structure)
        self.changes_log.append(
            "Updated project structure with auth and monitoring modules"
        )

        with open(file_path, "w") as f:
            f.write(content)

        print("✅ Applied structure updates to plan.md")

    def generate_validation_checklist(self):
        """Generate a validation checklist after remediation"""
        checklist = """
## Post-Remediation Validation Checklist

### Security (Constitution Principle V)
- [ ] WebSocket server authentication tasks added (T018a, T018b)
- [ ] Dashboard client authentication tasks added (T030a, T030b)
- [ ] REST API authentication tasks added (T036a, T036b)
- [ ] Security requirements FR-019, FR-020, FR-021 added
- [ ] Auth module structure added to plan.md

### Missing Requirements Coverage
- [ ] Operator alerting tasks added (T042a, T042b, T042c) - FR-015
- [ ] Webhook implementation tasks added (T056-T060) - FR-016
- [ ] Accuracy monitoring module added to plan

### Edge Cases & Ambiguities
- [ ] Blockchain reorg handling specified
- [ ] Double-spend detection strategy defined
- [ ] Fee market spike recalibration documented
- [ ] Memory pressure handling detailed

### Cleanup
- [ ] FR-008 and FR-018 consolidated
- [ ] Task counts updated (66 total, 35 parallel)
- [ ] Project structure reflects all new modules

### Testing Coverage
- [ ] Each new module has corresponding test task
- [ ] Authentication has unit test coverage
- [ ] Integration tests cover auth flow

### Ready for Implementation
- [ ] All CRITICAL issues resolved
- [ ] All HIGH priority issues addressed
- [ ] Constitution compliance verified
- [ ] 100% requirement coverage achieved
"""

        checklist_path = self.base_path / "REMEDIATION_CHECKLIST.md"
        with open(checklist_path, "w") as f:
            f.write(checklist)

        print("✅ Generated validation checklist: REMEDIATION_CHECKLIST.md")

    def generate_summary_report(self):
        """Generate a summary of all changes made"""
        report = f"""
# Remediation Summary Report
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Files Modified
1. tasks.md - Added 11 new tasks for security and missing features
2. spec.md - Added 3 security requirements, expanded edge cases
3. plan.md - Updated project structure with auth modules

## Changes Applied
{chr(10).join(f"- {change}" for change in self.changes_log)}

## New Task Distribution
- Security/Auth Tasks: 6 (T018a, T018b, T030a, T030b, T036a, T036b)
- Operator Alerting: 3 (T042a, T042b, T042c)
- Webhook Support: 5 (T056-T060)

## Backup Location
All original files backed up to: {self.backup_dir}

## Next Steps
1. Review REMEDIATION_CHECKLIST.md
2. Validate all changes
3. Run tests to ensure no regressions
4. Begin implementation with security tasks first
"""

        report_path = self.base_path / "REMEDIATION_SUMMARY.md"
        with open(report_path, "w") as f:
            f.write(report)

        print("✅ Generated summary report: REMEDIATION_SUMMARY.md")
        return report

    def run(self):
        """Execute all remediation steps"""
        print("🚀 Starting Specification Remediation Script")
        print("=" * 60)

        try:
            # Create backups first
            self.backup_files()
            print()

            # Apply all edits
            print("📝 Applying remediation edits...")
            self.apply_tasks_security_edits()
            self.apply_spec_security_requirements()
            self.apply_plan_structure_updates()
            print()

            # Generate validation artifacts
            print("📋 Generating validation artifacts...")
            self.generate_validation_checklist()
            summary = self.generate_summary_report()

            print()
            print("=" * 60)
            print("✅ REMEDIATION COMPLETE!")
            print(f"   Backup location: {self.backup_dir}")
            print("   Review: REMEDIATION_CHECKLIST.md")
            print("   Summary: REMEDIATION_SUMMARY.md")
            print()
            print(
                "⚠️  IMPORTANT: Review all changes before proceeding with implementation"
            )
            print(
                "🔒 CRITICAL: Security tasks (T018a-T036b) must be implemented first!"
            )

            return True

        except Exception as e:
            print(f"❌ Error during remediation: {e}")
            print(f"   Backups available at: {self.backup_dir}")
            return False


def main():
    """Main entry point for remediation script"""
    import sys

    # Determine the base path
    if len(sys.argv) > 1:
        base_path = sys.argv[1]
    else:
        base_path = "/media/sam/1TB/UTXOracle/specs/005-mempool-whale-realtime"

    # Check if we're in the right directory
    if not os.path.exists(os.path.join(base_path, "tasks.md")):
        print(f"❌ Error: Cannot find tasks.md in {base_path}")
        print("   Please run from the feature specification directory")
        sys.exit(1)

    # Run remediation
    remediation = SpecificationRemediation(base_path)
    success = remediation.run()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
