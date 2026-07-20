class Chunker:
    @staticmethod
    def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[dict]:
        """Splits text into chunks of specified token limits with overlaps."""
        words = text.split()
        # Word counts approximation: 1 token ~= 0.75 words.
        # So 512 tokens is approx 384 words.
        # Overlap of 64 tokens is approx 48 words.
        word_chunk_size = int(chunk_size * 0.75)
        word_overlap = int(overlap * 0.75)
        
        if word_chunk_size <= 0:
            word_chunk_size = 1
        if word_overlap >= word_chunk_size:
            word_overlap = word_chunk_size // 2
            
        chunks = []
        start = 0
        chunk_index = 0
        
        while start < len(words):
            end = start + word_chunk_size
            chunk_words = words[start:end]
            chunk_text = " ".join(chunk_words)
            token_count = int(len(chunk_words) / 0.75)
            
            chunks.append({
                "chunk_index": chunk_index,
                "text": chunk_text,
                "token_count": token_count
            })
            
            chunk_index += 1
            
            # Prevent infinite loops if loop doesn't advance
            advance = word_chunk_size - word_overlap
            if advance <= 0:
                advance = 1
                
            start += advance
            
        return chunks
