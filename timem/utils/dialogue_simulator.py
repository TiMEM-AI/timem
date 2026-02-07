"""
TiMem Dialogue Simulator

Used to simulate dialogue calls to TiMem service, evaluate if internal workflow is correct.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import time

from timem.workflows.memory_generation import run_memory_generation
from timem.utils.dataset_parser import LocomoDatasetParser, get_dataset_parser
from timem.utils.logging import get_logger

logger = get_logger(__name__)

class DialogueSimulator:
    """Dialogue simulator"""
    
    def __init__(self, data_dir: str = "data/locomo10_smart_split"):
        self.parser = get_dataset_parser(data_dir)
        self.logger = logging.getLogger(__name__)
        self.results = []
    
    async def simulate_single_conversation(self, session_id: str, 
                                         user_id: str = "test_user",
                                         expert_id: str = "test_expert",
                                         max_pairs: Optional[int] = None) -> Dict[str, Any]:
        """Simulate single conversation session"""
        try:
            # Load specified session
            file_path = f"data/locomo10_smart_split/locomo10_timem_{session_id}.json"
            session = self.parser.load_conversation_file(file_path)
            
            # Create dialogue pairs
            dialogue_pairs = self.parser.create_dialogue_pairs(session)
            
            if max_pairs:
                dialogue_pairs = dialogue_pairs[:max_pairs]
            
            self.logger.info(f"Starting dialogue session simulation: {session_id}, dialogue pairs: {len(dialogue_pairs)}")
            
            session_results = {
                "session_id": session_id,
                "sample_id": session.sample_id,
                "total_pairs": len(dialogue_pairs),
                "successful_calls": 0,
                "failed_calls": 0,
                "total_time": 0,
                "pair_results": []
            }
            
            start_time = time.time()
            
            for i, pair in enumerate(dialogue_pairs):
                try:
                    # Format dialogue pair as TiMem input
                    timem_input = self.parser.format_for_timem(
                        pair, user_id, expert_id
                    )
                    
                    # Call TiMem workflow
                    pair_start_time = time.time()
                    result = await run_memory_generation(timem_input)
                    pair_end_time = time.time()
                    
                    pair_result = {
                        "pair_index": i,
                        "turn_1": pair["turn_1"]["text"][:50] + "...",
                        "turn_2": pair["turn_2"]["text"][:50] + "...",
                        "success": result.get("success", False),
                        "memory_id": result.get("memory_id"),
                        "memory_layer": result.get("memory_layer"),
                        "quality_score": result.get("quality_score"),
                        "processing_time": pair_end_time - pair_start_time,
                        "error": result.get("error"),
                        "timestamp": result.get("timestamp")
                    }
                    
                    session_results["pair_results"].append(pair_result)
                    
                    if result.get("success", False):
                        session_results["successful_calls"] += 1
                    else:
                        session_results["failed_calls"] += 1
                        self.logger.warning(f"Dialogue pair {i} processing failed: {result.get('error')}")
                    
                    # Add delay to avoid overload
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    self.logger.error(f"Exception occurred while processing dialogue pair {i}: {e}")
                    session_results["failed_calls"] += 1
                    session_results["pair_results"].append({
                        "pair_index": i,
                        "success": False,
                        "error": str(e),
                        "processing_time": 0
                    })
            
            session_results["total_time"] = time.time() - start_time
            
            self.logger.info(f"Session {session_id} simulation completed: "
                           f"successful {session_results['successful_calls']}, "
                           f"failed {session_results['failed_calls']}, "
                           f"total time {session_results['total_time']:.2f}s")
            
            return session_results
            
        except Exception as e:
            self.logger.error(f"Simulating session {session_id} failed: {e}")
            return {
                "session_id": session_id,
                "error": str(e),
                "success": False
            }
    
    async def simulate_multiple_conversations(self, session_ids: List[str],
                                            user_id: str = "test_user",
                                            expert_id: str = "test_expert",
                                            max_pairs_per_session: Optional[int] = None) -> Dict[str, Any]:
        """Simulate multiple conversation sessions"""
        self.logger.info(f"Starting simulation of {len(session_ids)} conversation sessions")
        
        overall_results = {
            "total_sessions": len(session_ids),
            "successful_sessions": 0,
            "failed_sessions": 0,
            "total_pairs": 0,
            "total_successful_calls": 0,
            "total_failed_calls": 0,
            "total_time": 0,
            "session_results": []
        }
        
        start_time = time.time()
        
        for session_id in session_ids:
            session_result = await self.simulate_single_conversation(
                session_id, user_id, expert_id, max_pairs_per_session
            )
            
            overall_results["session_results"].append(session_result)
            
            if session_result.get("success", True):  # Default successful
                overall_results["successful_sessions"] += 1
                overall_results["total_pairs"] += session_result.get("total_pairs", 0)
                overall_results["total_successful_calls"] += session_result.get("successful_calls", 0)
                overall_results["total_failed_calls"] += session_result.get("failed_calls", 0)
            else:
                overall_results["failed_sessions"] += 1
        
        overall_results["total_time"] = time.time() - start_time
        
        # Calculate statistics
        if overall_results["total_pairs"] > 0:
            overall_results["success_rate"] = overall_results["total_successful_calls"] / overall_results["total_pairs"]
            overall_results["avg_time_per_pair"] = overall_results["total_time"] / overall_results["total_pairs"]
        else:
            overall_results["success_rate"] = 0
            overall_results["avg_time_per_pair"] = 0
        
        self.logger.info(f"Multi-session simulation completed: "
                        f"session success rate {overall_results['successful_sessions']}/{overall_results['total_sessions']}, "
                        f"dialogue pair success rate {overall_results['success_rate']:.2%}, "
                        f"total time {overall_results['total_time']:.2f}s")
        
        return overall_results
    
    async def benchmark_workflow_performance(self, test_sessions: List[str] = None,
                                           max_pairs_per_session: int = 5) -> Dict[str, Any]:
        """Workflow performance benchmark test"""
        if test_sessions is None:
            # Use default test sessions
            test_sessions = ["conv-26_session_1", "conv-27_session_1"]
        
        self.logger.info("Starting workflow performance benchmark test")
        
        benchmark_results = await self.simulate_multiple_conversations(
            test_sessions, max_pairs_per_session=max_pairs_per_session
        )
        
        # Add performance metrics
        benchmark_results["performance_metrics"] = {
            "throughput_pairs_per_second": benchmark_results["total_pairs"] / benchmark_results["total_time"] if benchmark_results["total_time"] > 0 else 0,
            "avg_memory_generation_time": benchmark_results["avg_time_per_pair"],
            "reliability_score": benchmark_results["success_rate"],
            "error_rate": 1 - benchmark_results["success_rate"]
        }
        
        return benchmark_results
    
    def generate_test_report(self, results: Dict[str, Any]) -> str:
        """Generate test report"""
        report = []
        report.append("=" * 60)
        report.append("TiMem Workflow Test Report")
        report.append("=" * 60)
        report.append(f"Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Total sessions: {results['total_sessions']}")
        report.append(f"Successful sessions: {results['successful_sessions']}")
        report.append(f"Failed sessions: {results['failed_sessions']}")
        report.append(f"Total dialogue pairs: {results['total_pairs']}")
        report.append(f"Successful calls: {results['total_successful_calls']}")
        report.append(f"Failed calls: {results['total_failed_calls']}")
        report.append(f"Success rate: {results.get('success_rate', 0):.2%}")
        report.append(f"Total time: {results['total_time']:.2f} seconds")
        report.append(f"Average time per dialogue pair: {results.get('avg_time_per_pair', 0):.3f} seconds")
        
        if "performance_metrics" in results:
            metrics = results["performance_metrics"]
            report.append("\nPerformance metrics:")
            report.append(f"  Throughput: {metrics['throughput_pairs_per_second']:.2f} dialogue pairs/second")
            report.append(f"  Average memory generation time: {metrics['avg_memory_generation_time']:.3f} seconds")
            report.append(f"  Reliability score: {metrics['reliability_score']:.2%}")
            report.append(f"  Error rate: {metrics['error_rate']:.2%}")
        
        # Detailed session results
        report.append("\nDetailed session results:")
        for session_result in results.get("session_results", []):
            report.append(f"  Session {session_result['session_id']}: "
                        f"successful {session_result.get('successful_calls', 0)}, "
                        f"failed {session_result.get('failed_calls', 0)}, "
                        f"time {session_result.get('total_time', 0):.2f} seconds")
        
        report.append("=" * 60)
        return "\n".join(report)

async def run_dialogue_simulation(session_ids: List[str] = None,
                                max_pairs_per_session: int = 5,
                                user_id: str = "test_user",
                                expert_id: str = "test_expert") -> Dict[str, Any]:
    """Convenience function to run dialogue simulation"""
    simulator = DialogueSimulator()
    
    if session_ids is None:
        # Use default test sessions
        session_ids = ["conv-26_session_1"]
    
    results = await simulator.simulate_multiple_conversations(
        session_ids, user_id, expert_id, max_pairs_per_session
    )
    
    # Generate report
    report = simulator.generate_test_report(results)
    print(report)
    
    return results

if __name__ == "__main__":
    # Example usage
    async def main():
        # Test single session
        results = await run_dialogue_simulation(
            session_ids=["conv-26_session_1"],
            max_pairs_per_session=3
        )
        
        # Save results to file
        import json
        with open("dialogue_simulation_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    
    asyncio.run(main())