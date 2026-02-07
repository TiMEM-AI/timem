#!/usr/bin/env python3
"""
Dataset Splitter Utility
Provides convenient functions to split raw dataset files into organized directory structures.

Usage:
    python experiments/dataset_utils/dataset_splitter.py --help
    python experiments/dataset_utils/dataset_splitter.py --split-locomo
    python experiments/dataset_utils/dataset_splitter.py --split-longmemeval
    python experiments/dataset_utils/dataset_splitter.py --split-all
"""

import argparse
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.dataset_utils.locomo.locomo_parser import LocomoParser
from experiments.dataset_utils.longmemeval.longmemeval_loader import LongMemEvalSQuestionLoader


def split_locomo_dataset(
    raw_json_path: str = "data/locomo10.json",
    output_dir: str = "data/locomo10_smart_split"
) -> bool:
    """
    Split Locomo dataset from raw JSON to organized session files
    
    Args:
        raw_json_path: Path to raw locomo10.json file
        output_dir: Output directory for split files
    
    Returns:
        True if successful, False otherwise
    """
    print(f"\n{'='*80}")
    print(f"🔄 Splitting Locomo Dataset")
    print(f"{'='*80}")
    
    try:
        parser = LocomoParser(output_dir)
        success = parser.split_dataset_from_json(raw_json_path, output_dir)
        
        if success:
            print(f"✅ Locomo dataset splitting completed successfully")
            print(f"   Output directory: {output_dir}")
        else:
            print(f"❌ Locomo dataset splitting failed")
        
        return success
        
    except Exception as e:
        print(f"❌ Error splitting Locomo dataset: {e}")
        import traceback
        traceback.print_exc()
        return False


def split_longmemeval_dataset(
    raw_json_path: str = "data/longmemeval_s_cleaned.json",
    output_dir: str = "data/longmemeval_s_split"
) -> bool:
    """
    Split LongMemEval-S dataset from raw JSON to organized directory structure
    
    Args:
        raw_json_path: Path to raw longmemeval_s_cleaned.json file
        output_dir: Output directory for split files
    
    Returns:
        True if successful, False otherwise
    """
    print(f"\n{'='*80}")
    print(f"🔄 Splitting LongMemEval-S Dataset")
    print(f"{'='*80}")
    
    try:
        loader = LongMemEvalSQuestionLoader(output_dir)
        success = loader.split_dataset_from_json(raw_json_path, output_dir)
        
        if success:
            print(f"✅ LongMemEval-S dataset splitting completed successfully")
            print(f"   Output directory: {output_dir}")
        else:
            print(f"❌ LongMemEval-S dataset splitting failed")
        
        return success
        
    except Exception as e:
        print(f"❌ Error splitting LongMemEval-S dataset: {e}")
        import traceback
        traceback.print_exc()
        return False


def split_all_datasets() -> bool:
    """
    Split both Locomo and LongMemEval-S datasets
    
    Returns:
        True if both successful, False otherwise
    """
    print(f"\n{'='*80}")
    print(f"🚀 Splitting All Datasets")
    print(f"{'='*80}")
    
    locomo_success = split_locomo_dataset()
    longmemeval_success = split_longmemeval_dataset()
    
    if locomo_success and longmemeval_success:
        print(f"\n{'='*80}")
        print(f"🎉 All datasets split successfully!")
        print(f"{'='*80}")
        print(f"✅ Locomo: data/locomo10_smart_split")
        print(f"✅ LongMemEval-S: data/longmemeval_s_split")
        print(f"{'='*80}\n")
        return True
    else:
        print(f"\n{'='*80}")
        print(f"⚠️ Some datasets failed to split")
        print(f"{'='*80}")
        print(f"{'✅' if locomo_success else '❌'} Locomo: data/locomo10_smart_split")
        print(f"{'✅' if longmemeval_success else '❌'} LongMemEval-S: data/longmemeval_s_split")
        print(f"{'='*80}\n")
        return False


def main():
    """Main function for command line interface"""
    parser = argparse.ArgumentParser(
        description="Split TiMem datasets from raw JSON files to organized directory structures",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Split Locomo dataset
  python dataset_utils/dataset_splitter.py --split-locomo
  
  # Split LongMemEval-S dataset
  python dataset_utils/dataset_splitter.py --split-longmemeval
  
  # Split both datasets
  python dataset_utils/dataset_splitter.py --split-all
  
  # Custom paths
  python dataset_utils/dataset_splitter.py --split-locomo \\
    --locomo-input data/my_locomo.json \\
    --locomo-output data/my_locomo_split
        """
    )
    
    # Action options
    parser.add_argument(
        "--split-locomo", 
        action="store_true",
        help="Split Locomo dataset"
    )
    parser.add_argument(
        "--split-longmemeval", 
        action="store_true",
        help="Split LongMemEval-S dataset"
    )
    parser.add_argument(
        "--split-all", 
        action="store_true",
        help="Split both datasets"
    )
    
    # Locomo options
    parser.add_argument(
        "--locomo-input",
        default="data/locomo10.json",
        help="Path to raw Locomo JSON file (default: data/locomo10.json)"
    )
    parser.add_argument(
        "--locomo-output",
        default="data/locomo10_smart_split",
        help="Output directory for Locomo split (default: data/locomo10_smart_split)"
    )
    
    # LongMemEval options
    parser.add_argument(
        "--longmemeval-input",
        default="data/longmemeval_s_cleaned.json",
        help="Path to raw LongMemEval-S JSON file (default: data/longmemeval_s_cleaned.json)"
    )
    parser.add_argument(
        "--longmemeval-output",
        default="data/longmemeval_s_split",
        help="Output directory for LongMemEval-S split (default: data/longmemeval_s_split)"
    )
    
    args = parser.parse_args()
    
    # Check if no action specified
    if not (args.split_locomo or args.split_longmemeval or args.split_all):
        parser.print_help()
        return 1
    
    success = True
    
    # Execute requested actions
    if args.split_all:
        success = split_all_datasets()
    else:
        if args.split_locomo:
            locomo_success = split_locomo_dataset(args.locomo_input, args.locomo_output)
            success = success and locomo_success
        
        if args.split_longmemeval:
            longmemeval_success = split_longmemeval_dataset(args.longmemeval_input, args.longmemeval_output)
            success = success and longmemeval_success
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
