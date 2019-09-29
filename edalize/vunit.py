import logging
import pathlib
from jinja2 import ChoiceLoader, FileSystemLoader
from edalize.edatool import Edatool

logger = logging.getLogger(__name__)

class Vunit(Edatool):

    _description = "VUnit is a FOSS project to facilitate continuous and automated testing of HDL code."
    tool_options = {'flags'   : {},
                    'members' : {'pre_flow_fragment'  : 'String',
                                 'post_flow_fragment' : 'String'},
                    'lists'   : {'vuargs' : 'String'}}
    argtypes = []

    @classmethod
    def get_doc(cls, api_ver):
        if api_ver == 0:
            return {'description' : cls._description,
                    'flags' : [],
                    'members' : [
                        {'name' : 'pre_flow_fragment',
                         'type' : 'String',
                         'desc' : 'Python script fragment, inserted into the run.py before the fileset files are added.'},
                        {'name' : 'post_flow_fragment',
                         'type' : 'String',
                         'desc' : 'Python script fragment, inserted into the run.py after the fileset files are added.'}],
                    'lists' : [
                        {'name' : 'vuargs',
                         'type' : 'String',
                         'desc' : 'Options appended to the tool invocation "python run.py" on the command line. e.g. --vuargs="--list"'},
                        ]}

    def configure_main(self):
        """ Generate the run-script for the tool. For VUnit, this is the run.py script."""

        # Ensure all src_files have a library to be compiled into
        # Files without a 'logical_name' attribute are compiled into 'default_lib'
        libraries = ['default_lib']
        for f in self.files:
            if f['logical_name'] == '':
                f['logical_name'] = 'default_lib'
            if f['logical_name'] not in libraries:
                libraries.append(f['logical_name'])

        def check_for_optional_files(self, opt):
            for f in self.files:
                if self.tool_options[opt] in f['name']:
                    # The f['name'] element is relative to the work root, so resolve to find the true path
                    abspath = (pathlib.Path(self.work_root) / pathlib.Path(f['name'])).resolve()

                    # Create a new Jinja2 loader from the filesystem
                    loader = ChoiceLoader([
                        getattr(self.jinja_env, 'loader'),
                        FileSystemLoader(str(abspath.parent.as_posix()))])
                    self.jinja_env.loader = loader

                    # Add the file to the options list, relative to the FSL
                    self.tool_options[opt] = abspath.name

                    return
            # Reach this exception after searching all files without success...
            raise Exception('{} file not found in target filesets'.format(opt))

        # If required, check for the pre/post flow fragment files within the filesets...
        for opt,arg in self.tool_options.copy().items():
            if opt in ['pre_flow_fragment', 'post_flow_fragment']:
                check_for_optional_files(self, opt)

        # Assemble the template-file data
        (src_files, incdirs) = self._get_fileset_files()
        template_vars = {
            'src_files'    : src_files,
            'libraries'    : libraries,
            'tool_options' : self.tool_options,
        }

        # Render the run.py template
        self.render_template('run.py.j2',
                             'run.py',
                             template_vars)

    def build_main(self):
        """ Invoke the run-script, executing only a compile operation """
        cmd = 'python'
        args = ['run.py', '--compile', '-k']
        self._run_tool(cmd, args)

    def run_main(self):
        """ Invoke the run-script, executing all tests discovered within the filesets """
        cmd = 'python'
        args = ['run.py'] + self.tool_options.get('vuargs', [])
        self._run_tool(cmd, args)
