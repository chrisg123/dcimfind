import sys
import os
import time
import datetime
import argparse
import logging
import re
from typing import List, Callable
import exiftool
import tty
import termios
from inspect import cleandoc

EXT_IMG=['.jpg']
EXT_VID=['.mp4']

KEY_ENTER  = 0x0d
KEY_CTRL_C = 0x03
KEY_CTRL_L = 0x0c
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('dir', help="Search directory")
    parser.add_argument('-c', '--copy', metavar='DIR',  help="Copy files to DIR")
    parser.add_argument('-i', '--interactive', action='store_true', help="Interactive mode")
    parser.add_argument('-v', '--verbosity', action='count', help="Verbosity level", default=0)
    parser.add_argument('--log-utc', action='store_true', help="Log timestamp as utc time")
    parser.add_argument('-r', '--regex',  metavar='REGEX', dest='regex',
                        help="Regex for file name matches",
                        default=(".*(%s)" % '|'.join(map(re.escape, EXT_IMG+EXT_VID))))
    parser.add_argument('--imgviewer', help="Image viewer application")
    parser.add_argument('--vidviewer', help="Video viewer application")
    parser.add_argument('--pager', help="Video viewer application",
                        default=('less' if os.name == 'posix' else None))

    args = parser.parse_args()
    interactive = args.interactive
    log_level = get_log_level(args.verbosity)
    rootpath = os.path.realpath(args.dir)
    regex = args.regex
    imgviewer = args.imgviewer
    vidviewer = args.vidviewer
    pager = args.pager

    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)
    ch = logging.StreamHandler(sys.stdout)
    fm = DtFormatter(fmt='%(asctime)s %(message)s', datefmt='%Y-%m-%dT%H:%M:%S.%f%z')
    if args.log_utc: fm.timezone = datetime.timezone.utc
    ch.setFormatter(fm)
    logger.addHandler(ch)

    if args.interactive: logger.info("*** Interactive mode ***")
    logger.debug("log_level == %d (%s)", log_level,logging.getLevelName(log_level))
    logger.debug("rootpath == '%s'", rootpath)
    logger.debug("regex == %s", regex)
    logger.debug("imgviewer == %s", imgviewer)
    logger.debug("vidviewer == %s", vidviewer)
    logger.debug("pager == %s", pager)

    files = get_files(rootpath, regex, interactive, imgviewer, vidviewer, pager)

    print_files(files)
    return 0

def get_files(
        rootpath: str,
        regex: str,
        interactive: bool,
        imgviewer: str,
        vidviewer: str,
        pager: str
) -> List[str]:
    if interactive: sys.stdout.write(get_main_cmds())
    selected_files = []
    skipped_files = []
    count = 0
    cmds = [KEY_ENTER, KEY_CTRL_C, KEY_CTRL_L, 'h','m','v','s','l', 'k','z','r','f','w']

    for root, _, files in os.walk(rootpath):
        select_folder = False
        for name in files:
            count += 1
            if not re.match(regex, name): continue
            filepath = os.path.join(root, name)

            if not interactive or select_folder:
                selected_files.append(filepath)
                continue
            while True:
                cmd = None
                def onchar(ch, _):
                    nonlocal cmd
                    if ord(ch) not in cmds and ch not in cmds: return False
                    cmd = ch
                    return True
                prompt = "(%d) '%s': " %(count, name)
                hinput(prompt, onchar)
                if ord(cmd) == KEY_CTRL_C:
                    sys.stdout.write("\nexit\n")
                    sys.exit(0)
                if ord(cmd) == KEY_ENTER:
                    skipped_files.append(filepath)
                    break
                if ord(cmd) == KEY_CTRL_L:
                    clear_terminal()
                    sys.stdout.write(get_main_cmds())
                    continue
                if cmd == 'h':
                    sys.stdout.write('\n' + get_main_cmds())
                    continue
                if cmd == 'm' and pager != None:
                    m = get_metadata(filepath).items()
                    lines = ["%s%s\n" %(k.ljust(40,'.'),v) for k,v in m]
                    os.system('cat <<"EOF"|%s\n%s\nEOF' %(pager, ''.join(lines)))
                    continue
                if cmd == 'v':
                    if is_img(filepath) and imgviewer != None:
                        os.system("%s '%s' > /dev/null 2>&1" %
                                  (imgviewer, filepath.replace("'","\'")))
                    elif is_vid(filepath) and vidviewer != None:
                        os.system("%s '%s' > /dev/null 2>&1" %
                                  (vidviewer, filepath.replace("'","\'")))
                    continue
                if cmd == 's':
                    selected_files.append(filepath)
                    break
                if cmd == 'l':
                    sys.stdout.write("\nSelected ")
                    print_files(selected_files)
                    continue
                if cmd == 'k':
                    sys.stdout.write("\nSkipped ")
                    print_files(skipped_files)
                    continue
                if cmd == 'z':
                    filelist_edit(skipped_files, selected_files, "Skipped")
                    continue
                if cmd == 'r':
                    filelist_edit(selected_files, skipped_files, "Selected")
                    continue
                if cmd == 'f':
                    select_folder = True
                    break
                if cmd == 'w':
                    sys.stdout.write("\r%s\r" % ' ' * len(prompt))
                    sys.stdout.write("%s\n" % filepath)
                    sys.stdout.flush()
                    continue

    return selected_files

def filelist_edit(src: List[str], dest: List[str], title: str):
    clear_terminal()
    loop = True
    while loop:
        if len(src) == 0:
            clear_terminal()
            sys.stdout.write(get_main_cmds())
            break
        sys.stdout.write("\n%s " % title)
        print_files(src)
        sys.stdout.write(get_filelist_cmds())

        def onchar(ch, _):
            nonlocal loop
            if ord(ch) == KEY_CTRL_C:
                clear_terminal()
                sys.stdout.write(get_main_cmds())
                loop = False
                return True
            if ord(ch) == KEY_CTRL_L:
                clear_terminal()
                return True

        inpt = hinput("Number: ", onchar)
        if inpt.isnumeric():
            idx = int(inpt)-1
            if not idx < len(src):
                clear_terminal()
                continue
            sf = src.pop(idx)
            dest.append(sf)
            clear_terminal()
            sys.stdout.write("  >> %d. %s\n" %(idx+1,sf))
            sys.stdout.flush()
        elif loop:
            clear_terminal()

def get_main_cmds() -> str:
    return """\
Commands:
  h - print this list of commands
  m - metadata
  v - view
  s - select
  f - select all in folder
  l - list all selected
  k - list all skipped
  r - remove a previously selected file
  z - select a previously skipped file
  w - print full path to file

Or hit 'enter' to skip

"""

def get_filelist_cmds() -> str:
    return """\
Enter number or CTRL+c to return
"""

def clear_terminal():
    print (u"{}[2J{}[;H".format(chr(27), chr(27)), end="")

def get_metadata(filepath: str) -> dict:
    with exiftool.ExifTool() as et:
        return et.get_metadata(filepath)

def is_img(filepath: str) -> bool:
    return os.path.splitext(filepath)[-1] in EXT_IMG

def is_vid(filepath: str) -> bool:
    return os.path.splitext(filepath)[-1] in EXT_VID

def print_files(files: List[str]):
    str_out = "Files (%d):\n" % len(files)
    for i,f in enumerate(files):
        str_out = str_out + ("%d. %s\n" %(i+1,f))
    print(str_out)

def get_log_level(verbosity: int) -> int:
    if   verbosity > 2 : return logging.DEBUG
    elif verbosity > 1 : return logging.INFO
    elif verbosity > 0 : return logging.WARNING
    else               : return logging.ERROR

def file_prompt(count: str, name: str, clear: int=0):
    prompt = "(%d) '%s': " %(count, name)
    sys.stdout.write("%s%s%s" %('\r'," "*(len(prompt)+clear), '\r'))
    sys.stdout.write(prompt)
    sys.stdout.flush()


def hinput(prompt: str=None, hook: Callable[[str,str], bool]=None) -> str:
    """input with a hook for char-by-char processing."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    inpt = ""
    while True:
        sys.stdout.write('\r')
        if prompt is not None:
            sys.stdout.write(prompt)
        sys.stdout.write(inpt)
        sys.stdout.flush()

        ch = None
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

        if hook is not None and hook(ch, inpt):
            break

        if ord(ch) == 0x7f: #BACKSPACE
            if len(inpt) > 0:
                sys.stdout.write('\b \b')
                inpt = inpt[:-1]
            continue

        if ord(ch) == 0x0d: #ENTER
            sys.stdout.write('\n')
            sys.stdout.flush()
            break

        if ch.isprintable():
            inpt += ch

    return inpt

class DtFormatter(logging.Formatter):
    timezone = None
    def converter(self, tstamp):
        return datetime.datetime.fromtimestamp(tstamp)
    def formatTime(self, record, datefmt=None):
        time = self.converter(record.created).astimezone(self.timezone)
        if datefmt:
            s = time.strftime(datefmt)
        else:
            t = time.strftime(self.default_time_format)
            s = self.default_msec_format % (t, record.msecs)
        return s

if __name__ == '__main__':
    exitCode = 0
    try:
        exitCode = main()
    except KeyboardInterrupt:
        print("\nexit")
    sys.exit(exitCode)
