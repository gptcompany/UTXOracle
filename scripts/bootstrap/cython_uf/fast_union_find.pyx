# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
"""Cython-optimized Union-Find for address clustering.

Compile with: cythonize -i fast_union_find.pyx
"""

import numpy as np
cimport numpy as np
from libc.stdlib cimport malloc, free

ctypedef np.int32_t INT32
ctypedef np.int8_t INT8

cdef class FastUnionFind:
    """Memory-efficient Union-Find using numpy arrays with Cython speedup."""

    cdef np.ndarray parent
    cdef np.ndarray rank
    cdef int size
    cdef int max_size
    cdef INT32[:] parent_view
    cdef INT8[:] rank_view

    def __init__(self, int max_size):
        self.max_size = max_size
        self.parent = np.arange(max_size, dtype=np.int32)
        self.rank = np.zeros(max_size, dtype=np.int8)
        self.parent_view = self.parent
        self.rank_view = self.rank
        self.size = max_size

    cdef inline int _find(self, int x) noexcept nogil:
        """Find root with path compression (no GIL)."""
        cdef int root = x
        cdef int next_x

        # Find root
        while self.parent_view[root] != root:
            root = self.parent_view[root]

        # Path compression
        while self.parent_view[x] != root:
            next_x = self.parent_view[x]
            self.parent_view[x] = root
            x = next_x

        return root

    def find(self, int x):
        """Python-accessible find."""
        return self._find(x)

    cdef inline bint _union(self, int x, int y) noexcept nogil:
        """Union by rank (no GIL). Returns True if merge happened."""
        cdef int root_x = self._find(x)
        cdef int root_y = self._find(y)

        if root_x == root_y:
            return False

        # Union by rank
        if self.rank_view[root_x] < self.rank_view[root_y]:
            self.parent_view[root_x] = root_y
        elif self.rank_view[root_x] > self.rank_view[root_y]:
            self.parent_view[root_y] = root_x
        else:
            self.parent_view[root_y] = root_x
            self.rank_view[root_x] += 1

        return True

    def union(self, int x, int y):
        """Python-accessible union."""
        return self._union(x, y)

    def process_pairs(self, np.ndarray[INT32, ndim=2] pairs):
        """Process batch of pairs. Returns number of unions performed."""
        cdef int n = pairs.shape[0]
        cdef int unions = 0
        cdef int i
        cdef INT32[:, :] pairs_view = pairs

        with nogil:
            for i in range(n):
                if self._union(pairs_view[i, 0], pairs_view[i, 1]):
                    unions += 1

        return unions

    def process_id_pairs(self, np.ndarray[INT32, ndim=1] ids1, np.ndarray[INT32, ndim=1] ids2):
        """Process two arrays of IDs as pairs."""
        cdef int n = ids1.shape[0]
        cdef int unions = 0
        cdef int i
        cdef INT32[:] view1 = ids1
        cdef INT32[:] view2 = ids2

        with nogil:
            for i in range(n):
                if self._union(view1[i], view2[i]):
                    unions += 1

        return unions

    def get_parent_array(self):
        """Return parent array for serialization."""
        return self.parent

    def get_rank_array(self):
        """Return rank array for serialization."""
        return self.rank

    def memory_usage_gb(self):
        """Return memory usage in GB."""
        return (self.parent.nbytes + self.rank.nbytes) / (1024**3)
