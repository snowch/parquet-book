# pyarrow reads row group 2 of the same file, from a file that prints each read it gets.
import io
import pyarrow.parquet as pq

class Logged(io.RawIOBase):
    def __init__(self, path): self.data, self.at = open(path, "rb").read(), 0
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.at
    def seek(self, offset, whence=0):
        self.at = [offset, self.at + offset, len(self.data) + offset][whence]
        return self.at
    def readinto(self, buffer):
        n = min(len(buffer), len(self.data) - self.at)
        buffer[:n] = self.data[self.at : self.at + n]
        print(f"  read {n} bytes at {self.at}")
        self.at += n
        return n

for pre_buffer in (False, True):  # pyarrow's default is True
    file = Logged("fixtures/pruning-sorted.parquet")
    print(f"open, pre_buffer={pre_buffer}:")
    parquet = pq.ParquetFile(file, pre_buffer=pre_buffer)
    print("read row group 2:")
    rows = parquet.read_row_groups([2]).num_rows  # try pq.read_table(file, filters=...)
    print(f"{rows} rows")
