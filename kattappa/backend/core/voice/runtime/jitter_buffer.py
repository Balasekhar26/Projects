"""Jitter Buffer (Program 31.0).

Mitigates audio package delivery time variance by buffer queue sorting,
sequence alignment, and playout delay control.
"""
from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Tuple


class JitterBuffer:
    """Buffers out-of-order packets and paces audio playback to avoid stuttering."""

    def __init__(self, target_delay_packets: int = 3) -> None:
        self.target_delay = target_delay_packets
        # Min-heap queue: stores tuples (seq_num, data)
        self.heap: List[Tuple[int, bytes]] = []
        self.seen_seqs: set[int] = set()
        self.last_popped_seq: Optional[int] = None

    def push(self, seq_num: int, data: bytes) -> None:
        """Pushes a new packet into the jitter buffer, sorting by sequence number."""
        if seq_num in self.seen_seqs:
            return  # skip duplicate packets
        
        # Discard late packets arriving after we already popped them
        if self.last_popped_seq is not None and seq_num <= self.last_popped_seq:
            return

        heapq.heappush(self.heap, (seq_num, data))
        self.seen_seqs.add(seq_num)

    def pop(self, force: bool = False) -> Optional[bytes]:
        """Pops the next packet if the buffer has met its target delay size or force is True.

        If the buffer is empty or size is below target_delay (and force is False),
        returns None to simulate initial buffering pause.
        """
        if not self.heap:
            return None

        # Pop immediately if we have buffered enough packets or force is requested
        if force or len(self.heap) >= self.target_delay:
            seq, data = heapq.heappop(self.heap)
            self.last_popped_seq = seq
            return data

        return None

    def clear(self) -> None:
        """Clears all buffered packets."""
        self.heap.clear()
        self.seen_seqs.clear()
        self.last_popped_seq = None

    @property
    def size(self) -> int:
        return len(self.heap)
