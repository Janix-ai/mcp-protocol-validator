#!/usr/bin/env python3
# Copyright (c) 2025 Scott Wilcox
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Generate a compliance report for an MCP server.

This script runs tests against any MCP server and generates a detailed compliance report.
It adapts to the server's capabilities rather than having fixed expectations.

Environment Variables:
    MCP_SKIP_SHUTDOWN:     Set to 'true' to skip calling the shutdown method
    MCP_PROTOCOL_VERSION:  Set the protocol version to test against
    MCP_REQUIRED_TOOLS:    Comma-separated list of required tools
    
    Server-specific environment variables can be set in two ways:
    1. Set the variable directly, e.g., BRAVE_API_KEY=your_key
    2. Use MCP_DEFAULT_* prefix for default values, e.g., MCP_DEFAULT_BRAVE_API_KEY=default_key
    
    The script will warn about missing required environment variables for specific servers.

Server Configurations:
    The system uses configuration files in the 'server_configs' directory to determine:
    - Required environment variables for each server
    - Tests that should be skipped
    - Required tools for the server
    - Recommended protocol version
    
    To support a new server, add a JSON configuration file to the 'server_configs' directory.
    See the README.md file in that directory for details on the configuration format.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add the parent directory to the Python path
parent_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(parent_dir))

from mcp_testing.utils.runner import run_tests
from mcp_testing.utils.reporter import results_to_markdown, extract_server_name, generate_markdown_report
from mcp_testing.tests.base_protocol.test_initialization import TEST_CASES as INIT_TEST_CASES
from mcp_testing.tests.features.test_tools import TEST_CASES as TOOLS_TEST_CASES
from mcp_testing.tests.features.test_async_tools import TEST_CASES as ASYNC_TOOLS_TEST_CASES
from mcp_testing.tests.features.dynamic_tool_tester import TEST_CASES as DYNAMIC_TOOL_TEST_CASES
from mcp_testing.tests.features.dynamic_async_tools import TEST_CASES as DYNAMIC_ASYNC_TEST_CASES
from mcp_testing.tests.specification_coverage import TEST_CASES as SPEC_COVERAGE_TEST_CASES

# Import server compatibility utilities
try:
    from mcp_testing.utils.server_compatibility import (
        is_shutdown_skipped,
        prepare_environment_for_server,
        get_server_specific_test_config,
        get_recommended_protocol_version
    )
except ImportError:
    # Fallback implementations if module doesn't exist yet
    def is_shutdown_skipped() -> bool:
        """Check if shutdown should be skipped based on environment variable."""
        skip_shutdown = os.environ.get("MCP_SKIP_SHUTDOWN", "").lower()
        return skip_shutdown in ("true", "1", "yes")
    
    def prepare_environment_for_server(server_command: str) -> dict:
        """Prepare environment variables for a specific server."""
        env_vars = os.environ.copy()
        if "server-brave-search" in server_command:
            env_vars["MCP_SKIP_SHUTDOWN"] = "true"
        return env_vars
    
    def get_server_specific_test_config(server_command: str) -> dict:
        """Get server-specific test configuration."""
        config = {}
        if "server-brave-search" in server_command:
            config["skip_tests"] = ["test_shutdown", "test_exit_after_shutdown"]
            config["required_tools"] = ["brave_web_search", "brave_local_search"]
        return config
    
    def get_recommended_protocol_version(server_command: str) -> str:
        """Get the recommended protocol version for a specific server."""
        if "server-brave-search" in server_command:
            return "2024-11-05"
        return None

def log_with_timestamp(message):
    """Log a message with a timestamp prefix."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

# Create a custom test runner that adds additional logging
class VerboseTestRunner:
    """A custom test runner that provides more detailed progress logs."""
    
    def __init__(self, debug=False):
        self.debug = debug
        self.start_time = time.time()
        
    async def run_test_with_progress(self, test_func, server_command, protocol_version, test_name, env_vars, 
                                    current, total):
        """Run a single test with progress reporting."""
        test_start_time = time.time()
        log_with_timestamp(f"Running test {current}/{total}: {test_name}")
        
        from mcp_testing.utils.runner import MCPTestRunner
        runner = MCPTestRunner(debug=self.debug)
        try:
            result = await runner.run_test(test_func, server_command, protocol_version, test_name, env_vars)
        except Exception as e:
            # Handle exceptions that might occur during test execution
            result = {
                "name": test_name,
                "passed": False,
                "message": f"Test runner exception: {str(e)}",
                "duration": time.time() - test_start_time
            }
            
        test_end_time = time.time()
        elapsed = test_end_time - test_start_time
        
        # Ensure result is a dictionary
        if not isinstance(result, dict):
            log_with_timestamp(f"Warning: Test {test_name} returned non-dictionary result: {result}")
            result = {
                "name": test_name,
                "passed": False,
                "message": f"Invalid test result: {str(result)}",
                "duration": elapsed
            }
        
        status = "PASSED" if result.get("passed", False) else "FAILED"
        if result.get("skipped", False):
            status = "SKIPPED"
            
        log_with_timestamp(f"Test {current}/{total}: {test_name} - {status} ({elapsed:.2f}s)")
        
        total_elapsed = test_end_time - self.start_time
        remaining = total_elapsed / current * (total - current) if current > 0 else 0
        log_with_timestamp(f"Progress: {current}/{total} tests completed, time elapsed: {total_elapsed:.1f}s, estimated remaining: {remaining:.1f}s")
        
        return result
        
    async def run_tests(self, tests, protocol, server_command, env_vars, timeout=None):
        """Run a list of test cases with detailed progress reporting."""
        test_results = []
        total_tests = len(tests)
        
        log_with_timestamp(f"Starting test suite with {total_tests} tests")
        self.start_time = time.time()
        
        for idx, (test_func, test_name) in enumerate(tests, 1):
            result = await self.run_test_with_progress(
                test_func, server_command, protocol, test_name, env_vars, idx, total_tests
            )
            test_results.append(result)
            
        total_time = time.time() - self.start_time
        
        # Count passed, failed, and skipped tests, handling non-dictionary results
        passed = 0
        skipped = 0
        for r in test_results:
            if isinstance(r, dict):
                if r.get("passed", False):
                    if "skipped" in r.get("message", "").lower():
                        skipped += 1
                    else:
                        passed += 1
                if r.get("skipped", False):
                    skipped += 1
        
        failed = total_tests - passed - skipped
        
        log_with_timestamp(f"Test suite completed: {passed} passed, {failed} failed, {skipped} skipped, total time: {total_time:.2f}s")
        
        # Format the results exactly like the standard runner does
        return {
            "results": test_results,
            "total": total_tests,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "timeouts": 0 if timeout is None else 1
        }

async def main():
    """Run the compliance tests and generate a report."""
    parser = argparse.ArgumentParser(description="Generate an MCP server compliance report")
    
    # Server configuration
    parser.add_argument("--server-command", required=True, help="Command to start the server")
    parser.add_argument("--protocol-version", choices=["2024-11-05", "2025-03-26"], 
                        default="2025-03-26", help="Protocol version to use")
    parser.add_argument("--server-config", help="JSON file with server-specific test configuration")
    parser.add_argument("--args", help="Additional arguments to pass to the server command")
    
    # Output options
    parser.add_argument("--output-dir", default="reports", help="Directory to store the report files")
    parser.add_argument("--report-prefix", default="cr", help="Prefix for report filenames (default: 'cr')")
    parser.add_argument("--json", action="store_true", help="Generate a JSON report")
    
    # Debug and control options
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--skip-async", action="store_true", help="Skip async tests")
    parser.add_argument("--skip-shutdown", action="store_true", help="Skip shutdown/exit tests")
    parser.add_argument("--required-tools", help="Comma-separated list of tools that should be required")
    parser.add_argument("--skip-tests", help="Comma-separated list of test names to skip")
    parser.add_argument("--dynamic-only", action="store_true", help="Only run dynamic tools tests")
    parser.add_argument("--test-mode", choices=["all", "core", "tools", "async", "spec"], default="all", 
                      help="Test mode: all, core, tools, async, or spec")
    parser.add_argument("--spec-coverage-only", action="store_true", 
                      help="Only run tests for spec coverage")
    parser.add_argument("--auto-detect", action="store_true", 
                      help="Auto-detect server type and apply appropriate configuration")
    parser.add_argument("--test-timeout", type=int, default=30,
                      help="Timeout in seconds for individual tests")
    parser.add_argument("--tools-timeout", type=int, default=30,
                      help="Timeout in seconds for tools tests (which often take more time)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    
    args = parser.parse_args()
    
    # Combine server command with any additional arguments
    full_server_command = args.server_command
    if args.args:
        full_server_command = f"{args.server_command} {args.args}"
    
    # Auto-detect protocol version if requested
    if args.auto_detect:
        recommended_version = get_recommended_protocol_version(full_server_command)
        if recommended_version:
            if args.debug:
                log_with_timestamp(f"Auto-detected protocol version {recommended_version} for {args.server_command}")
            args.protocol_version = recommended_version
    
    # Set environment variables for the server
    log_with_timestamp(f"Preparing environment for server: {full_server_command}")
    
    # Get environment variables with server-specific settings
    env_vars = prepare_environment_for_server(full_server_command)
    
    # Set protocol version in environment
    env_vars["MCP_PROTOCOL_VERSION"] = args.protocol_version
    
    # Set skip_shutdown flag in environment if specified via command line
    if args.skip_shutdown:
        env_vars["MCP_SKIP_SHUTDOWN"] = "true"
        log_with_timestamp("Shutdown will be skipped (--skip-shutdown flag)")
    elif is_shutdown_skipped():
        # Environment variable is already set
        log_with_timestamp("Shutdown will be skipped (MCP_SKIP_SHUTDOWN env var)")
    
    # Parse server configuration if provided
    server_config = {}
    if args.server_config:
        try:
            with open(args.server_config, 'r') as f:
                server_config = json.load(f)
                log_with_timestamp(f"Loaded server configuration from {args.server_config}")
        except Exception as e:
            log_with_timestamp(f"Error loading server configuration: {str(e)}")
    
    # If auto-detect is enabled, get server-specific config
    if args.auto_detect:
        server_specific_config = get_server_specific_test_config(full_server_command)
        server_config.update(server_specific_config)
        if args.debug and server_specific_config:
            log_with_timestamp(f"Auto-detected configuration for {args.server_command}")
            for key, value in server_specific_config.items():
                log_with_timestamp(f"  {key}: {value}")
    
    # Parse required tools
    required_tools = []
    if args.required_tools:
        required_tools = [t.strip() for t in args.required_tools.split(',')]
    elif server_config.get("required_tools"):
        required_tools = server_config.get("required_tools")
    
    # Set required tools in environment
    if required_tools:
        env_vars["MCP_REQUIRED_TOOLS"] = ",".join(required_tools)
        log_with_timestamp(f"Required tools: {', '.join(required_tools)}")
    
    # Parse tests to skip
    skip_tests = []
    if args.skip_tests:
        skip_tests = [t.strip() for t in args.skip_tests.split(',')]
    elif server_config.get("skip_tests"):
        skip_tests = server_config.get("skip_tests")
    
    if skip_tests:
        log_with_timestamp(f"Skipping tests: {', '.join(skip_tests)}")
    
    # Ensure output directory exists
    output_dir = os.path.join(parent_dir, args.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate timestamp for report filenames
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Collect test cases based on test mode and flags
    tests = []
    
    if args.dynamic_only:
        log_with_timestamp("Running in dynamic-only mode - tests will adapt to the server's capabilities")
        tests.extend(INIT_TEST_CASES)  # Always include initialization tests
        tests.extend(DYNAMIC_TOOL_TEST_CASES)
        
        if args.protocol_version == "2025-03-26" and not args.skip_async:
            tests.extend(DYNAMIC_ASYNC_TEST_CASES)
    
    elif args.spec_coverage_only:
        log_with_timestamp("Running specification coverage tests only")
        tests.extend(SPEC_COVERAGE_TEST_CASES)
    
    else:
        # Normal mode - collect tests based on test_mode
        if args.test_mode in ["all", "core"]:
            tests.extend(INIT_TEST_CASES)
            
        if args.test_mode in ["all", "tools"]:
            tests.extend(TOOLS_TEST_CASES)
            
        if args.test_mode in ["all", "async"] and args.protocol_version == "2025-03-26" and not args.skip_async:
            tests.extend(ASYNC_TOOLS_TEST_CASES)
            
        if args.test_mode in ["all", "spec"]:
            tests.extend(SPEC_COVERAGE_TEST_CASES)
    
    # Filter out tests to skip
    if skip_tests:
        original_count = len(tests)
        tests = [(func, name) for func, name in tests if name not in skip_tests]
        skipped_count = original_count - len(tests)
        if skipped_count > 0:
            log_with_timestamp(f"Skipped {skipped_count} tests based on configuration")
    
    log_with_timestamp(f"Running compliance tests for protocol {args.protocol_version}...")
    log_with_timestamp(f"Server command: {full_server_command}")
    log_with_timestamp(f"Test mode: {args.test_mode}")
    log_with_timestamp(f"Total tests to run: {len(tests)}")
    
    # Run the tests
    start_time = time.time()
    
    # Set timeouts based on arguments
    test_timeout = args.test_timeout
    tools_timeout = args.tools_timeout
    
    if args.verbose or True:  # Always use verbose logging
        # Use our custom verbose test runner
        runner = VerboseTestRunner(debug=args.debug)
        
        # Group tests by type and run with appropriate timeouts
        tool_tests = [(func, name) for func, name in tests if name.startswith("test_tool_") or name.startswith("test_tools_")]
        non_tool_tests = [(func, name) for func, name in tests if not (name.startswith("test_tool_") or name.startswith("test_tools_"))]
        
        # Run non-tool tests first with standard timeout
        if non_tool_tests:
            log_with_timestamp(f"Running {len(non_tool_tests)} non-tool tests with {test_timeout}s timeout")
            non_tool_results = await runner.run_tests(
                non_tool_tests, 
                args.protocol_version, 
                full_server_command, 
                env_vars,
                timeout=test_timeout
            )
        else:
            non_tool_results = {"results": [], "total": 0, "passed": 0, "failed": 0, "skipped": 0}
        
        # Run tool tests with extended timeout
        if tool_tests:
            log_with_timestamp(f"Running {len(tool_tests)} tool tests with {tools_timeout}s timeout")
            tool_results = await runner.run_tests(
                tool_tests, 
                args.protocol_version, 
                full_server_command, 
                env_vars,
                timeout=tools_timeout
            )
        else:
            tool_results = {"results": [], "total": 0, "passed": 0, "failed": 0, "skipped": 0}
        
        # Combine results
        results = {
            "results": non_tool_results["results"] + tool_results["results"],
            "total": non_tool_results["total"] + tool_results["total"],
            "passed": non_tool_results["passed"] + tool_results["passed"],
            "failed": non_tool_results["failed"] + tool_results["failed"],
            "skipped": non_tool_results["skipped"] + tool_results["skipped"],
            "timeouts": non_tool_results.get("timeouts", 0) + tool_results.get("timeouts", 0)
        }
    else:
        # Use the standard test runner
        from mcp_testing.utils.runner import MCPTestRunner
        runner = MCPTestRunner(debug=args.debug)
        results = await run_tests(
            tests, 
            args.protocol_version, 
            "stdio", 
            full_server_command, 
            env_vars,
            debug=args.debug,
            timeout=tools_timeout  # Use the longer timeout for all tests in non-verbose mode
        )
    
    # Calculate summary information - Ensure results is a dictionary with the right fields
    if isinstance(results, dict) and 'total' in results:
        # Results is already in the right format
        total_tests = results['total']
        passed_tests = results['passed']
        failed_tests = results['failed']
    else:
        # Handle case where results might be a list of individual test results
        total_tests = len(results)
        passed_tests = 0
        for r in results:
            if isinstance(r, dict) and r.get("passed", False):
                passed_tests += 1
        failed_tests = total_tests - passed_tests
        # Convert to dictionary format
        results = {
            "results": results,
            "total": total_tests,
            "passed": passed_tests,
            "failed": failed_tests
        }
    
    # Calculate compliance percentage
    if isinstance(results, dict) and 'skipped' in results:
        # Exclude skipped tests from the total when calculating compliance
        adjusted_total = total_tests - results['skipped']
        compliance_percentage = (passed_tests / adjusted_total) * 100 if adjusted_total > 0 else 100
    else:
        compliance_percentage = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
    
    # Determine compliance status
    if compliance_percentage == 100:
        compliance_status = "✅ Fully Compliant"
    elif compliance_percentage >= 80:
        compliance_status = "⚠️ Mostly Compliant"
    else:
        compliance_status = "❌ Non-Compliant"
    
    log_with_timestamp("\nCompliance Test Results:")
    log_with_timestamp(f"Total tests: {total_tests}")
    log_with_timestamp(f"Passed: {passed_tests}")
    log_with_timestamp(f"Failed: {failed_tests}")
    if isinstance(results, dict) and 'skipped' in results:
        log_with_timestamp(f"Skipped: {results['skipped']}")
    log_with_timestamp(f"Compliance Status: {compliance_status} ({compliance_percentage:.1f}%)")
    
    # Extract server name from the command (for report purposes)
    server_name = extract_server_name(full_server_command)
    
    # Generate the report filename - always use "cr_" prefix for consistency
    report_basename = f"cr_{server_name}_{args.protocol_version}_{timestamp}"
    
    if args.json:
        # Generate JSON report
        json_report = {
            "server": server_name,
            "protocol_version": args.protocol_version,
            "timestamp": timestamp,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "compliance_percentage": compliance_percentage,
            "compliance_status": compliance_status,
            "results": results
        }
        
        json_report_path = os.path.join(output_dir, f"{report_basename}.json")
        with open(json_report_path, 'w') as f:
            json.dump(json_report, f, indent=2)
        
        log_with_timestamp(f"JSON report saved to: {json_report_path}")
    
    # Generate markdown report
    try:
        # Create a basic markdown report ourselves instead of using the generate_markdown_report function
        markdown_lines = [
            f"# {server_name} MCP Compliance Report",
            "",
            "## Server Information",
            "",
            f"- **Server Command**: `{full_server_command}`",
            f"- **Protocol Version**: {args.protocol_version}",
            f"- **Test Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ""
        ]
        
        # Add server config if available
        if server_config:
            markdown_lines.extend([
                "## Server Configuration",
                ""
            ])
            
            for key, value in server_config.items():
                markdown_lines.append(f"- **{key}**: {value}")
            markdown_lines.append("")
        
        # Add summary section
        markdown_lines.extend([
            "## Summary",
            "",
            f"- **Total Tests**: {results['total']}",
            f"- **Passed**: {results['passed']} ({(results['passed'] / results['total'] * 100) if results['total'] > 0 else 0:.1f}%)",
            f"- **Failed**: {results['failed']} ({(results['failed'] / results['total'] * 100) if results['total'] > 0 else 0:.1f}%)",
            ""
        ])
        
        # Add compliance status
        if results['failed'] == 0:
            markdown_lines.append(f"**Compliance Status**: ✅ Fully Compliant (100.0%)")
        elif results['passed'] / results['total'] >= 0.8:
            markdown_lines.append(f"**Compliance Status**: ⚠️ Mostly Compliant ({results['passed'] / results['total'] * 100:.1f}%)")
        else:
            markdown_lines.append(f"**Compliance Status**: ❌ Non-Compliant ({results['passed'] / results['total'] * 100:.1f}%)")
        
        # Add detailed test results
        markdown_lines.extend([
            "",
            "## Detailed Results",
            "",
            "### Passed Tests",
            ""
        ])
        
        # Add passed tests
        passed_tests = []
        for r in results['results']:
            if isinstance(r, dict) and r.get('passed', False):
                passed_tests.append(r)
        
        if passed_tests:
            markdown_lines.append("| Test | Duration | Message |")
            markdown_lines.append("|------|----------|---------|")
            for test in passed_tests:
                test_name = test.get('name', '').replace('test_', '').replace('_', ' ').title()
                duration = f"{test.get('duration', 0):.2f}s"
                message = test.get('message', '')
                markdown_lines.append(f"| {test_name} | {duration} | {message} |")
        else:
            markdown_lines.append("No tests passed.")
        
        markdown_lines.extend([
            "",
            "### Failed Tests",
            ""
        ])
        
        # Add failed tests
        failed_tests = []
        for r in results['results']:
            if isinstance(r, dict) and not r.get('passed', False):
                failed_tests.append(r)
            elif not isinstance(r, dict):
                # Handle non-dictionary results (like strings)
                failed_tests.append({
                    "name": "Unknown Test",
                    "passed": False,
                    "message": f"Invalid test result format: {str(r)}",
                    "duration": 0
                })
        
        if failed_tests:
            markdown_lines.append("| Test | Duration | Error Message |")
            markdown_lines.append("|------|----------|--------------|")
            for test in failed_tests:
                test_name = test.get('name', '').replace('test_', '').replace('_', ' ').title()
                duration = f"{test.get('duration', 0):.2f}s"
                message = test.get('message', '')
                markdown_lines.append(f"| {test_name} | {duration} | {message} |")
        else:
            markdown_lines.append("All tests passed! 🎉")
            
        # Generate and write the report
        markdown_content = "\n".join(markdown_lines)
        markdown_report_path = os.path.join(output_dir, f"{report_basename}.md")
        with open(markdown_report_path, 'w') as f:
            f.write(markdown_content)
        
        log_with_timestamp(f"Markdown compliance report generated: {markdown_report_path}")
    except Exception as e:
        log_with_timestamp(f"Error generating markdown report: {str(e)}")
        if args.debug:
            import traceback
            traceback.print_exc()
    
    # Set exit code based on compliance
    return 0 if compliance_percentage == 100 else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        log_with_timestamp("Testing interrupted by user")
        sys.exit(130)
    except Exception as e:
        log_with_timestamp(f"Error running compliance tests: {str(e)}")
        sys.exit(1) 