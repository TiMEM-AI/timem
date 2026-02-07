## **Data Sources**

This directory contains the raw dataset files required for TiMem experiments. The following two files should be placed in this folder:

### **Required Files**

1. **[locomo10.json]

   - **Source**: Locomo Dataset
   - **Download**: github repository of snap-research/locomo
   - **Description**: Data for the Locomo dataset
2. **[longmemeval_s_cleaned.json]

   - **Source**: LongMemEval-S Dataset
   - **Download**: github repository of xiaowu0162/LongMemEval
   - **Description**: Data for longmemeval_s

### **Usage**

After downloading these files:

1. Place them directly in the [data/](TiMem_demo/data:0:0-0:0) directory
2. Run the dataset splitter to generate organized experiment data:
   ```bash
   python experiments/dataset_utils/dataset_splitter.py --split-all
   ```

### **Generated Structure**

The splitter will create:

- [locomo10_smart_split/] - Organized Locomo session files and metadata
- [longmemeval_s_split/] - Organized LongMemEval-S user data and question types
