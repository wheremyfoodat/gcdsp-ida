"""
gcdsp.py
~~~~~~~~

An IDAPython processor module for the GC/Wii DSP.

Copyright (C) 2011 Pierre Bourdon <delroth@lse.epita.fr>
Copyright (C) 2011 Stephane Sezer <stephane@lse.epita.fr>

Licensed under the GPLv2 license, see the LICENSE file at the root of this
repository.
"""
from idaapi import *
import os.path

GREETINGS_STRING = """\
GC/Wii DSP processor for IDA (C) 2011 LSE (http://www.lse.epita.fr/) - \
licensed under the GPLv2 license\
"""

class OpType:
    """Enumeration of the different operand encoding types which can be found
    in the GC DSP ISA. From DSPTables.h in Dolphin source code."""

    NONE = 0
    VAL = 1
    IMM = 2
    MEM = 3
    STR = 4
    ADDR_I = 5
    ADDR_D = 6

    REG = 0x8000
    REG04 = REG | 0x0400
    REG08 = REG | 0x0800
    REG18 = REG | 0x1800
    REGM18 = REG18
    REG19 = REG | 0x1900
    REGM19 = REG19
    REG1A = REG | 0x1a80
    REG1C = REG | 0x1c00
    ACCL = REG | 0x1c00
    ACCM = REG | 0x1e00
    ACCM_D = REG | 0x1e80
    ACC = REG | 0x2000
    ACC_D = REG | 0x2080
    AX = REG | 0x2200
    REGS_MASK = 0x3f80

    REF = REG | 0x4000
    PRG = REF | REG


# Get autogenerated parts from another file
exec(open(os.path.join(os.path.dirname(__file__), 'gcdsp_generated.py')).read())

class Operand(object):
    def __init__(self, type, size, loc, rshift, mask):
        self.type = type
        self.size = size
        self.loc = loc
        self.rshift = rshift
        self.mask = mask

    def parse(self, res, byte1, byte2):
        """Parses informations about the operand from the two instruction
        bytes. Code mostly from Dolphin version of DSPTool's disassemble.cpp
        file, translated into Python.

        Puts return value into `res` (which is an IDA op_t)."""

        val = byte1 if not self.loc else byte2
        val &= self.mask

        if self.rshift < 0:
            val <<= -self.rshift
        else:
            val >>= self.rshift

        type = self.type
        if type & OpType.REG:
            if type in (OpType.ACC_D, OpType.ACCM_D):
                val = (~val & 0x1) | ((type & OpType.REGS_MASK) >> 8)
            else:
                val |= (type & OpType.REGS_MASK) >> 8
            type &= ~OpType.REGS_MASK

        if type == OpType.REG:
            res.type = o_reg
            res.dtyp = dt_byte  # TODO: fix (ACCs are 40-bit for example)
            res.reg = val
        elif type == OpType.PRG:
            res.type = o_phrase
            res.dtyp = dt_byte
            res.phrase = val
        elif type == OpType.ADDR_I:
            res.type = o_near
            res.dtyp = dt_byte
            res.addr = val
        elif type == OpType.ADDR_D:
            res.type = o_mem
            res.dtyp = dt_byte
            res.addr = val
        elif type == OpType.IMM:
            res.type = o_imm
            res.dtyp = dt_byte
            res.value = val
        elif type == OpType.MEM:
            if self.size != 2:
                b = val & 0x80
                if b:
                    val |= 0xFF00
            res.type = o_mem
            res.dtyp = dt_byte
            res.addr = val
        else:
            raise ValueError("unhandled type: %04X" % type)

class Instr(object):
    def __init__(self, name, opcode, mask, size, operands=[], ext_operands=[], cmt='',
                 stops=False, calls=False, jumps=False, shifts=False,
                 hll=False):
        self.name = name

        self.operands = operands
        self.ext_operands = ext_operands
        self.all_operands = operands + ext_operands

        self.all_ops_parsed = [Operand(*o) for o in self.all_operands]

        self.cmt = cmt

        self.stops = stops
        self.calls = calls
        self.jumps = jumps
        self.shifts = shifts
        self.hll = hll

        self.opcode = opcode
        self.mask = mask
        self.size = size

    def __str__(self):
        return "<Instr: %s (%04X & %04X)>" % (self.name, self.opcode,
                                              self.mask)

    @property
    def flags(self):
        ret = 0
        for i, operand in enumerate(self.all_operands):
            ret |= CF_USE1 << i  # TODO: CF_CHG ?
        if self.stops:
            ret |= CF_STOP
        if self.calls:
            ret |= CF_CALL
        if self.jumps:
            ret |= CF_JUMP
        if self.shifts:
            ret |= CF_SHFT
        if self.hll:
            ret |= CF_HLL
        return ret

class GCDSPProcessor(processor_t):
    id = 0x8000 + 5854
    flag = PR_ADJSEGS | PRN_HEX | PR_WORD_INS
    cnbits = 16
    dnbits = 16
    psnames = ["gcdsp"]
    plnames = ["GC/Wii DSP"]
    segreg_size = 0

    instruc_start = 0
    cmd = insn_t()

    assembler = {
        "flag" : ASH_HEXF3 | ASD_DECF0 | ASO_OCTF1 | ASB_BINF3
               | AS_ASCIIC | AS_ASCIIZ,
        "uflag": 0,
        "name": "GNU assembler",

        "origin": ".org",
        "end": "end",
        "cmnt": ";",

        "ascsep": '"',
        "accsep": "'",
        "esccodes": "\"'",

        "a_ascii": ".ascii",
        "a_byte": ".word",
        "a_word": ".dword",

        "a_bss": "dfs %s",

        "a_seg": "seg",
        "a_curip": ".",
        "a_public": "",
        "a_weak": "",
        "a_extrn": ".extrn",
        "a_comdef": "",
        "a_align": ".align",

        "lbrace": "(",
        "rbrace": ")",
        "a_mod": "%",
        "a_band": "&",
        "a_bor": "|",
        "a_xor": "^",
        "a_bnot": "~",
        "a_shl": "<<",
        "a_shr": ">>",
        "a_sizeof_fmt": "size %s",
    }

    regStrings = [
        "AR0", "AR1", "AR2", "AR3",
        "IX0", "IX1", "IX2", "IX3",
        "WR0", "WR1", "WR2", "WR3",
        "ST0", "ST1", "ST2", "ST3",
        "AC0.H", "AC1.H",
        "CR", "SR",
        "PROD.L", "PROD.M1", "PROD.H", "PROD.M2",
        "AX0.L", "AX1.L", "AX0.H", "AX1.H",
        "AC0.L", "AC1.L", "AC0.M", "AC1.M",
        "ACC0", "ACC1",
        "AX0", "AX1",
        "CS", "DS"
    ]

    reg_names = regNames = ["$%s" % n for n in regStrings]

    def __init__(self):
        processor_t.__init__(self)
        self._init_instructions()
        self._init_registers()

    def _add_instruction(self, instr):
        base = instr.opcode & instr.mask
        limit = instr.mask ^ 0xFFFF
        for opcode in range(base, base + limit + 1):
            if (opcode & instr.mask) == instr.opcode:
                self.instrs_opcode[opcode] = instr
        self.instrs_list.append(instr)

    def _init_instructions(self):
        """Setup instructions parameters for IDA."""
        self.instrs_opcode = [None] * 0x10000
        self.instrs_list = []

        for op in opcodes:
            stops = op[0] in ("RET", "RTI", "HALT", "JMP", "JMPR")
            jumps = op[0].startswith("J")
            calls = op[0].startswith("CALL")
            instr = Instr(op[0], op[1], op[2], op[3], op[5], cmt=op[8],
                          stops=stops, jumps=jumps, calls=calls)

            if op[6]:  # extended
                ext_7bit = (instr.opcode & 0xF000) == 0x3000
                for ext in opcodes_ext[1:]:  # skip not extended
                    if ext_7bit and ext[1] >= 0x80:
                        continue
                    new_name = instr.name + "'" + ext[0]
                    new_opcode = instr.opcode | ext[1]
                    new_mask = instr.mask | ext[2]
                    new_cmt = op[8] + '; ' + ext[8]
                    xinstr = Instr(new_name, new_opcode, new_mask, instr.size,
                                   instr.operands, ext_operands=ext[5], cmt=new_cmt,
                                   stops=stops, jumps=jumps, calls=calls)
                    self._add_instruction(xinstr)

                if ext_7bit:
                    instr.mask |= 0x7F
                else:
                    instr.mask |= 0xFF

            self._add_instruction(instr)

        self.instruc = [{ "name": i.name, "feature": i.flags }
                        for i in self.instrs_list]
        self.instruc_end = len(self.instruc)

        self.instrs = {}
        for instr in self.instrs_list:
            self.instrs[instr.name] = instr

        self.instrs_ids = {}
        for i, instr in enumerate(self.instrs_list):
            self.instrs_ids[instr.name] = i
            instr.id = i

    def _init_registers(self):
        """Setup registers index and special register values."""

        self.reg_ids = {}
        for i, reg in enumerate(self.reg_names):
            self.reg_ids[reg] = i

        # Create ireg_XXXX constants for registers
        for i in range(len(self.regStrings)):
            setattr(self, 'ireg_' + self.regStrings[i], i)

        # Simulate fake segment registers
        self.reg_first_sreg = self.reg_code_sreg = self.ireg_CS
        self.reg_last_sreg = self.reg_data_sreg = self.ireg_DS

    def notify_init(self, idp_file):
        """Called at module initialization."""
        cvar.inf.mf = True  # set to big endian... wtf
        cvar.inf.wide_high_byte_first = True  # big endian for 16b bytes too
        return True

    def notify_endbinary(self, ok):
        """Called when the binary finished loading."""
        if ok:
            print (GREETINGS_STRING)

    def _read_cmd_byte(self, instruction):
        ea = instruction.ea + instruction.size
        byte = get_wide_byte(ea)
        self.cmd.size += 1
        return byte

    def ev_ana_insn(self, instruction):
        """Analyze one instruction and fill the "cmd" instance member."""
        self.cmd = instruction
        byte1 = self._read_cmd_byte(self.cmd)
        instr = self.instrs_opcode[byte1]
        if instr is None:
            return 0

        if instr.size == 2:
            byte2 = self._read_cmd_byte(self.cmd)
        else:
            byte2 = 0

        operands = [self.cmd[i] for i in range(6)]
        for to_fill in operands:
            to_fill.type = o_void

        for (to_fill, op) in zip(operands, instr.all_ops_parsed):
            op.parse(to_fill, byte1, byte2)

        self.cmd.itype = instr.id
        return self.cmd.size

    def _emu_operand(self, instruction, op):
        """Emulated using one operand from the instruction."""
        if op.type == o_mem:
            instruction.create_op_data(op.addr, 0, op.dtype)
            instruction.add_dref(op.addr, 0, dr_R)  # TODO: dr_W ?
        elif op.type == o_near:
            if self.cmd.get_canon_feature() & CF_CALL:
                fl = fl_CN
            else:
                fl = fl_JN
            instruction.add_cref(op.addr, 0, fl)

    def ev_emu_insn (self, instruction):
        """Emulate instruction behavior and create x-refs, interpret operand
        values, etc."""
        self.cmd = instruction
        instr = self.instrs_list[self.cmd.itype]

        for i in range(len(instr.all_operands)):
            self._emu_operand(instruction, self.cmd[i])

        if not instr.stops:  # add a link to next instr if code continues
            instruction.add_cref(self.cmd.ea + self.cmd.size, 0, fl_F)

        return True

    def ev_out_operand (self, outctx, op):
        """Generates text representation of an instruction operand."""
        if op.type == o_reg:
            outctx.out_register(self.reg_names[op.reg])
        elif op.type == o_phrase:
            outctx.out_symbol('@')
            outctx.out_register(self.reg_names[op.reg])
        elif op.type == o_imm:
            outctx.out_value(op, OOFW_IMM)
        elif op.type in [o_near, o_mem]:
            ok = outctx.out_name_expr(op, op.addr, BADADDR)
            if not ok:
                outctx.out_tagon(COLOR_ERROR)
                outctx.out_long(op.addr, 16)
                outctx.out_tagoff(COLOR_ERROR)
                remember_problem(PR_NONAME, self.cmd.ea)
        else:
            return False
        return True

    def ev_out_insn (self, outctx):
        """Generates text representation of an instruction in the "cmd" inst
        member."""
        cmd = self.cmd

        outctx.out_mnem(15)  # max width = 15

        instr = self.instrs_list[cmd.itype]

        in_extended = False
        for i in range(0, 6):
            if cmd[i].type == o_void:
                break

            if i != 0:
                if not in_extended and i >= len(instr.operands):
                    in_extended = True
                    outctx.out_char(' ')
                    outctx.out_symbol(':')
                else:
                    outctx.out_symbol(',')
                outctx.out_char(' ')

            outctx.out_one_operand(i)

        #term_output_buffer()
        outctx.flush_outbuf()
        cvar.gl_comm = 1  # allow comments at end of line
        #outctx.out_line(buf)

    def notify_get_autocmt(self):
        return self.instrs_list[cmd.itype].cmt

def PROCESSOR_ENTRY():
    return GCDSPProcessor()
