import logging
import os
import pathlib
from jinja2 import ChoiceLoader, FileSystemLoader
from collections import OrderedDict

from edalize.edatool import Edatool

logger = logging.getLogger(__name__)

class Alintpro(Edatool):

    _description = " ALINT-PRO is a hdl design verification solution, primarily by static-analysis "

    tool_options = {'flags'   : {'gui' : 'Bool'},
                    'members' : {'linting_ruleset'  : 'String'},
                    'lists'   : {}}
    argtypes = []

    @classmethod
    def get_doc(cls, api_ver):
        if api_ver == 0:
            return {'description' : cls._description,
                    'flags' : [
                        {'name' : 'gui',
                         'type' : 'Bool',
                         'desc' : 'Run tool in a GUI environment'}],
                    'members' : [
                        {'name' : 'linting_ruleset',
                         'type' : 'String',
                         'desc' : 'Path to ruleset macro file'}],
                    'lists' : []}

    def configure_main(self):
        (src_files, incdirs) = self._get_fileset_files(force_slash=True)


        # Jinja2 #include files need to be defined relative to a FileSystemLoader, which is given the /src directory
        fsloader_path = (pathlib.Path(self.work_root).parent/'src')
        logger.debug('FileSystemLoader path : ' + fsloader_path.as_posix())
        loader = ChoiceLoader([
            getattr(self.jinja_env, 'loader'),
            FileSystemLoader(str(fsloader_path))])
        self.jinja_env.loader = loader

        waiver_files = [f for f in src_files if f.file_type == 'waiver']
        for f in waiver_files:

            abspath = (pathlib.Path(self.work_root) / pathlib.Path(f.name)).resolve()
            # Create a new Jinja2 loader from the filesystem
            loader = ChoiceLoader([
                getattr(self.jinja_env, 'loader'),
                FileSystemLoader(str(abspath.parent.as_posix()))])
            self.jinja_env.loader = loader
            # Change the waiver file name to be relative to the FSL
            f.name = abspath.name

            src_files.remove(f)

        template_vars = {
            'name'             : self.name.replace('.','_'),
            'toplevel'         : self.toplevel,
            'tool_options'     : self.tool_options,
            'src_files'        : src_files,
            'waiver_files'     : waiver_files,
        }

        self.render_template('alintpro.do.j2',
                             'alintpro.do',
                             template_vars)

    def build_main(self):
        pass

    def run_main(self):

        cmd = 'C:/Aldec/ALINT-PRO-2018.07-SU1/bin/'
        args = []
        if self.tool_options.get('gui', []):
            # TRUE
            cmd += 'alint.exe'
        else:
            # FALSE
            cmd += 'alintcon.exe'
            args += ['-batch']
        args += ['-do', 'alintpro.do']

        self._run_tool(cmd, args)
