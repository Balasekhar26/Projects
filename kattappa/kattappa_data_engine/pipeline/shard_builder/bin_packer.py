import os
import json
import numpy as np
import random

class BinPacker:
    def __init__(self, output_dir, train_ratio=0.96, val_ratio=0.02, test_ratio=0.02, sequence_length=1024):
        self.output_dir = output_dir
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        self.sequence_length = sequence_length
        
        # Output subdirs
        self.train_dir = os.path.join(output_dir, "train")
        self.val_dir = os.path.join(output_dir, "validation")
        self.test_dir = os.path.join(output_dir, "test")
        
        os.makedirs(self.train_dir, exist_ok=True)
        os.makedirs(self.val_dir, exist_ok=True)
        os.makedirs(self.test_dir, exist_ok=True)

    def group_by_duplicate_clusters(self, documents, duplicate_clusters):
        """
        Groups documents into 'meta-documents' using the duplicate clusters list 
        to enforce split isolation.
        """
        # Create mapping of doc_id -> root_id
        doc_to_root = {}
        for root_id, doc_ids in duplicate_clusters.items():
            for doc_id in doc_ids:
                doc_to_root[doc_id] = root_id
                
        # Group documents by root_id
        meta_docs = {}
        for doc in documents:
            doc_id = doc.get("id")
            root_id = doc_to_root.get(doc_id, doc_id)
            if root_id not in meta_docs:
                meta_docs[root_id] = []
            meta_docs[root_id].append(doc)
            
        return list(meta_docs.values())

    def split_and_pack(self, documents, duplicate_clusters, bpe_streamer):
        """
        Splits documents with cluster isolation, tokenizes them, 
        and serializes them into uint16 binary files and JSON index files.
        """
        meta_docs_list = self.group_by_duplicate_clusters(documents, duplicate_clusters)
        
        # Shuffle meta-documents to prevent topical skews
        random.seed(42)
        random.shuffle(meta_docs_list)
        
        # Estimate total tokens to partition splits
        tokenized_meta_docs = []
        total_tokens = 0
        
        print("Tokenizing documents and preparing packing stream...")
        for meta_doc in meta_docs_list:
            meta_tokens = []
            meta_doc_details = []
            
            for doc in meta_doc:
                content = doc.get("content", "")
                tokens = bpe_streamer.encode(content)
                meta_tokens.extend(tokens)
                
                # Save details for idx file
                meta_doc_details.append({
                    "id": doc.get("id"),
                    "source": doc.get("source"),
                    "macro_class": doc.get("macro_class"),
                    "token_count": len(tokens)
                })
                
            tokenized_meta_docs.append({
                "tokens": meta_tokens,
                "docs": meta_doc_details
            })
            total_tokens += len(meta_tokens)
            
        print(f"Total tokens across all documents: {total_tokens}")
        
        # Distribute based on token limits
        train_target = total_tokens * self.train_ratio
        val_target = total_tokens * self.val_ratio
        
        splits = {
            "train": {"tokens": [], "docs": []},
            "validation": {"tokens": [], "docs": []},
            "test": {"tokens": [], "docs": []}
        }
        
        current_tokens = 0
        for item in tokenized_meta_docs:
            tokens_len = len(item["tokens"])
            
            if current_tokens < train_target:
                split_name = "train"
            elif current_tokens < (train_target + val_target):
                split_name = "validation"
            else:
                split_name = "test"
                
            splits[split_name]["tokens"].extend(item["tokens"])
            splits[split_name]["docs"].extend(item["docs"])
            current_tokens += tokens_len
            
        # Pack and write binary files
        for split_name, data in splits.items():
            name_map = {"train": "train", "validation": "val", "test": "test"}
            prefix = name_map.get(split_name, "train")
            split_dir = getattr(self, f"{prefix}_dir")
            os.makedirs(split_dir, exist_ok=True)
            tokens_list = data["tokens"]
            docs_list = data["docs"]
            
            if not tokens_list:
                print(f"Warning: No tokens in split {split_name}")
                continue
                
            # Pack tokens into fixed sequence windows
            packed = bpe_streamer.pack_tokens(tokens_list, sequence_length=self.sequence_length)
            packed_flat = [tok for seq in packed for tok in seq]
            
            # Convert to numpy uint16 array
            tokens_array = np.array(packed_flat, dtype=np.uint16)
            
            # Paths
            bin_path = os.path.join(split_dir, "tokens.bin")
            idx_path = os.path.join(split_dir, "metadata.idx")
            
            # Write .bin
            tokens_array.tofile(bin_path)
            
            # Generate offsets for documents
            offsets = []
            current_offset = 0
            for doc_meta in docs_list:
                doc_meta["offset"] = current_offset
                current_offset += doc_meta["token_count"]
                offsets.append(doc_meta)
                
            # Write .idx
            idx_data = {
                "split": split_name,
                "total_tokens": len(tokens_list),
                "packed_sequences": len(packed),
                "sequence_length": self.sequence_length,
                "documents": offsets
            }
            with open(idx_path, 'w', encoding='utf-8') as f:
                json.dump(idx_data, f, indent=2)
                
            print(f"Split {split_name}: Wrote {len(packed)} sequences ({len(tokens_list)} raw tokens) to {bin_path}")
            
        return splits
