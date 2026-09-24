"""Small strict interpreter for the frozen movement-only SBPF bytecode slices.

Tests execute actual deployed instructions, independently of Python movement math.
This is not a full Solana VM: no syscalls, CPIs, program loading, or unbounded jumps.
"""
import struct

MASK = (1 << 64)-1


class SliceVM:
    def __init__(self, code, start):
        self.code, self.start = code, start
        self.memory = bytearray(262144)
        self.registers = [0]*11
        self.registers[10] = 200000
        self.next_address = 4096

    def allocate(self, size):
        address = self.next_address
        self.next_address += size
        if self.next_address >= 100000:
            raise ValueError('Slice memory budget exceeded')
        return address

    def write(self, address, value, size=8):
        if not 0 <= address <= len(self.memory)-size:
            raise ValueError('Invalid memory write')
        self.memory[address:address+size] = (value & ((1 << (size*8))-1)).to_bytes(size,'little')

    def read(self, address, size=8):
        if not 0 <= address <= len(self.memory)-size:
            raise ValueError('Invalid memory read')
        return int.from_bytes(self.memory[address:address+size],'little')

    def run(self):
        pc = self.start
        r = self.registers
        for _ in range(2000):
            if pc == self.start+len(self.code):
                return
            offset = pc-self.start
            if offset < 0 or offset+8 > len(self.code) or offset%8:
                raise ValueError(f'Jump outside verified slice: {pc:x}')
            op, regs, displacement, immediate = struct.unpack_from('<BBhi',self.code,offset)
            dst, src = regs & 15, regs >> 4
            if dst > 10 or src > 10:
                raise ValueError('Invalid register')
            pc += 8
            if op == 0x18:
                high = struct.unpack_from('<I',self.code,offset+12)[0]
                r[dst] = (immediate & 0xffffffff) | (high << 32)
                pc += 8
                continue
            cls, operation = op & 7, op >> 4
            size = {0:4,8:2,16:1,24:8}[op & 24]
            if cls == 1 and op & 0xe0 == 0x60:
                r[dst] = self.read(r[src]+displacement,size)
            elif cls in (2,3) and op & 0xe0 == 0x60:
                self.write(r[dst]+displacement,r[src] if cls==3 else immediate,size)
            elif cls in (4,7):
                bits = 32 if cls==4 else 64
                mask = (1 << bits)-1
                a = r[dst] & mask
                b = (r[src] if op & 8 else immediate) & mask
                if operation==0: value=a+b
                elif operation==1: value=a-b
                elif operation==2: value=a*b
                elif operation==3: value=a//b
                elif operation==4: value=a|b
                elif operation==5: value=a&b
                elif operation==6: value=a << (b & (bits-1))
                elif operation==7: value=a >> (b & (bits-1))
                elif operation==10: value=a^b
                elif operation==11: value=b
                else: raise ValueError(f'Unsupported ALU opcode {op:x}')
                r[dst]=value & mask
            elif cls==5:
                a,b = r[dst], (r[src] if op & 8 else immediate & MASK)
                if operation==9: return
                predicates = {0:True,1:a==b,2:a>b,3:a>=b,4:bool(a&b),5:a!=b,10:a<b,11:a<=b}
                if operation not in predicates:
                    raise ValueError(f'Unsupported jump opcode {op:x}')
                if predicates[operation]: pc += displacement*8
            else:
                raise ValueError(f'Unsupported slice opcode {op:x}')
        raise ValueError('Slice instruction budget exceeded')
