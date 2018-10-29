import logging
import os.path
import platform

from edalize.edatool import Edatool

logger = logging.getLogger(__name__)

""" Vivado Backend

The Vivado backend executes Xilinx Vivado to build systems and program the FPGA.

The backend defines the following section:

    [vivado]
    part = <part name> # Format <family><device><package>-<speedgrade>
    hw_device = <device name> # Format <family><device>_0
    top_module = <RTL module name>

A core (usually the system core) can add the following files:

- Standard design sources

- Constraints: Supply xdc files with file_type=xdc

- IP: Supply the IP core xci file with file_type=xci and other files (like .prj)
      as file_type=data
"""
class Vivado(Edatool):
    MAKEFILE_TEMPLATE = """NAME := {}

all: $(NAME).bit

$(NAME).bit:  $(NAME)_run.tcl $(NAME).xpr
	vivado -mode batch -source $^

$(NAME).xpr: $(NAME).tcl{}
	vivado -mode batch -source $<

%.edif: %.ys
	yosys -q -s $?

build-gui: $(NAME).xpr
	vivado $<
"""
    tool_options = {'members' : {'part' : 'String',
                                 'synth' : 'String'}}

    argtypes = ['vlogdefine', 'vlogparam']

    """ Configuration is the first phase of the build

    This writes the project TCL files and Makefile. It first collects all
    sources, IPs and contraints and then writes them to the TCL file along
     with the build steps.
    """
    def configure_main(self):
        synth = self.tool_options.get('synth', 'vivado')

        (src_files, incdirs) = self._get_fileset_files(force_slash=True)

        vivado_files = []
        for src_file in src_files:
            f = self.src_file_filter(src_file, synth)
            if f:
                vivado_files.append(f)

        edif = ""
        if synth == 'yosys':
            self._write_yosys_file()
            edif = " $(NAME).edif"
            vivado_files.append("read_edif {}.edif".format(self.toplevel))
            vivado_files.append("set_property design_mode GateLvl [current_fileset]")


        has_vhdl2008 = 'vhdlSource-2008' in [x.file_type for x in src_files]
        has_xci      = 'xci'             in [x.file_type for x in src_files]

        template_vars = {
            'name'         : self.name,
            'src_files'    : vivado_files,
            'incdirs'      : incdirs,
            'tool_options' : self.tool_options,
            'toplevel'     : self.toplevel,
            'vlogparam'    : self.vlogparam,
            'vlogdefine'   : self.vlogdefine,
            'has_vhdl2008' : has_vhdl2008,
            'has_xci'      : has_xci,
        }

        self.render_template('vivado-project.tcl.j2',
                             self.name+'.tcl',
                             template_vars)

        file_path = os.path.join(self.work_root, "Makefile")
        with open(file_path, 'w') as f:
            f.write(self.MAKEFILE_TEMPLATE.format(self.name, edif))

        self.render_template('vivado-run.tcl.j2',
                             self.name+"_run.tcl")

    def _write_yosys_file(self):
        # Write yosys script file
        (src_files, incdirs) = self._get_fileset_files()
        with open(os.path.join(self.work_root, self.name+'.ys'), 'w') as yosys_file:
            for key, value in self.vlogdefine.items():
                yosys_file.write("verilog_defines -D{}={}\n".format(key, self._param_value_str(value)))

            yosys_file.write("verilog_defaults -push\n")
            yosys_file.write("verilog_defaults -add -defer\n")
            if incdirs:
                yosys_file.write("verilog_defaults -add {}\n".format(' '.join(['-I'+d for d in incdirs])))

            for f in src_files:
                if f.file_type in ['verilogSource']:
                    yosys_file.write("read_verilog {}\n".format(f.name))
                elif f.file_type == 'user':
                    pass
            for key, value in self.vlogparam.items():
                _s = "chparam -set {} {} $abstract\{}\n"
                yosys_file.write(_s.format(key,
                                           self._param_value_str(value, '"'),
                                           self.toplevel))

            yosys_file.write("verilog_defaults -pop\n")
            yosys_file.write("synth_xilinx")
            yosys_synth_options = self.tool_options.get('yosys_synth_options', [])
            for option in yosys_synth_options:
                yosys_file.write(' ' + option)
            yosys_file.write(" -edif {}.edif".format(self.toplevel))
            if self.toplevel:
                yosys_file.write(" -top " + self.toplevel)
            yosys_file.write("\n")
            yosys_file.write("write_json {}.json\n".format(self.name))

    def src_file_filter(self, f, synth):
        def _vhdl_source(f):
            s = 'read_vhdl'
            if f.file_type == 'vhdlSource-2008':
                s += ' -vhdl2008'
            if f.logical_name:
                s += ' -library '+f.logical_name
            return s

        file_types = {
            'xci'                 : 'read_ip',
            'xdc'                 : 'read_xdc',
            'tclSource'           : 'source',
        }
        ignore_types = ['user']
        if synth == 'vivado':
            file_types.update({
                'verilogSource'       : 'read_verilog',
                'systemVerilogSource' : 'read_verilog -sv',
                'vhdlSource'          : _vhdl_source(f),
            })
        else:
            ignore_types += ['verilogSource', 'systemVerilogSource']
        _file_type = f.file_type.split('-')[0]
        if _file_type in file_types:
            return file_types[_file_type] + ' ' + f.name
        elif _file_type in ignore_types:
            return ''
        else:
            _s = "{} has unknown file type '{}'"
            logger.warning(_s.format(f.name,
                                     f.file_type))
        return ''

    """ Program the FPGA

    For programming the FPGA a vivado tcl script is written that searches for the
    correct FPGA board and then downloads the bitstream. The tcl script is then
    executed in Vivado's batch mode.
    """
    def run(self, remaining):
        tcl_file_name = self.name+"_pgm.tcl"
        self._write_program_tcl_file(tcl_file_name)
        self._run_tool('vivado', ['-mode', 'batch', '-source', tcl_file_name ])

    """ Write the programming TCL file """
    def _write_program_tcl_file(self, program_tcl_filename):
        template_vars = {}
        template_vars['bitstream_name'] = self.name+'.bit'
        template_vars['hw_device'] = self.tool_options['hw_device']

        template = self.jinja_env.get_template('vivado/vivado-program.tcl.j2')
        tcl_file_path = os.path.join(self.work_root, program_tcl_filename)
        with open(tcl_file_path, 'w') as program_tcl_file:
            program_tcl_file.write(template.render(template_vars))
