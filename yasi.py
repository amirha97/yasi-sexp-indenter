#!/usr/bin/env python
# coding: utf-8

""" yasi

Date: 20th November 2013
Author: nkmathew <kipkoechmathew@gmail.com>

Dialect aware s-expression indenter
"""

from __future__ import print_function

import argparse
import hashlib
import os
import re
import shutil
import sys
import time
import collections
import json

# pylint: disable=unused-import
from pprint import pprint

__version__ = '0.2.1'


def create_args_parser():
    """ Return command line parser """
    parser = argparse.ArgumentParser(
        description='Dialect-aware s-expression indenter', prog='yasi')
    parser.add_argument('files', help='List of files to be indented. '
                        'Will indent from standard input if no files are specified',
                        nargs='*')
    parser.add_argument(
        '-nc', '--no-compact', '--nc', dest='compact',
        help='Do not compact the code, just indent', action='store_false')
    parser.add_argument(
        '-nb', '--no-backup', '--nb', dest='backup', action='store_false',
        help='Do not create a backup file even if --backup-dir is specified ')
    parser.add_argument(
        '-nm', '--no-modify', '--nm', dest='modify',
        help='Do not modify the file', action='store_false')
    parser.add_argument(
        '-nw', '--no-warning', '--nw', dest='warning',
        help='Do not display warnings', action='store_false')
    parser.add_argument(
        '-no', '--no-output', '--no', dest='output',
        help='Suppress output of the indented code', action='store_false')
    parser.add_argument(
        '-ne', '--no-exit', '--ne', dest='exit', action='store_false',
        help='Instructs the program not to exit when a warning is raised.')
    parser.add_argument(
        '-o', dest='output_file',
        help='Path/name of output file', type=str, default='')
    parser.add_argument(
        '--dialect', '-dialect',
        help='Use Scheme keywords', type=str, default='all')
    parser.add_argument(
        '-v', '--version', action='version',
        help='Prints script version', version='yasi v%s' % __version__)
    parser.add_argument(
        '-bd', '--backup-dir', '--bd', '-backup-dir',
        help='The directory where the backup file is to be written',
        type=str, default=os.getcwd())
    parser.add_argument(
        '-is', '--indent-size', '--is',
        help='The number of spaces per indent',
        type=int, default=2)
    parser.add_argument(
        '-di', '--default-indent', '--di',
        help='The indent level to be used in case a ' +
        "function's argument is in the next line. Vim uses 2, the most common being 1.",
        type=int, default=1)
    parser.add_argument(
        '-ic', '--indent-comments', '--ic',
        help='If true, comment lines will be indented possibly ' +
        'messing with any deliberate comment layout', action='store_true')
    parser.add_argument(
        '-uni', '--uniform', '-uniform', '--uni',
        help='Dictates whether the if-clause and else-clause of an if-like' +
        'block should have the same indent level.',
        action='store_true')
    return parser


def parse_options(arguments=None):
    """ Reads command-line arguments

    >>> parse_options('--indent-comments')
    """
    if arguments is None:
        arguments = sys.argv[1:]
    if isinstance(arguments, str):
        arguments = arguments.split()
    if isinstance(arguments, argparse.Namespace):
        return arguments
    parser = create_args_parser()
    args = parser.parse_args(arguments)
    # pprint(args.__dict__)

    args.dialect = args.dialect.lower()
    if args.dialect not in ['lisp', 'newlisp', 'clojure', 'scheme', 'all', '']:
        parser.error("`{0}' is not a recognized dialect".format(args.dialect))

    args.backup_dir = os.path.expanduser(args.backup_dir)
    if not os.path.exists(args.backup_dir):
        parser.error("Directory `{0}' does not exist".format(args.backup_dir))

    if len(args.files) > 1 and args.output_file:
        parser.error('Cannot use the -o flag when more than one file is specified')

    if not args.files:
        # Indentation from standard input
        if args.modify and not args.output_file:
            args.modify = False
        args.backup = False
        args.warning = False

    return args


def read_file(fname):
    """ read_file(fname : str) -> str

    >>> read_file(r'C:\\mine\\test.lisp')
    r'(print "No, no, there\'s \\r\\nlife in him!. ")\\r\\n\\r\\n'

    The file is read in binary mode in order to preserve original line endings.
        Line ending    Binary mode Text mode
            CRLF            CRLF    LF
            CR              CR      LF
    """
    assert os.path.exists(fname), "\n--%s-- Warning: File `%s' does not exist. . ." \
        % (current_time(), fname)
    with open(fname, 'rb') as fp:
        return fp.read().decode('utf-8')


def current_time():
    """ current_time() -> str

    >>> current_time()
    14:28:04

    Returns the current local time in 24 clock system.
    """
    return time.strftime('%X', (time.localtime()))


def backup_source_file(fname, options=None):
    """ backup_source_file(fname : str)

    >>> backup_source_file('~/Desktop/lisp/test.lisp')

    Create a backup copy of the source file.
    """
    opts = parse_options(options)
    backup_dir = opts.backup_dir
    assert os.path.exists(fname), \
        ("\n--%s-- Warning: File `%s' does not exist. . ." % (current_time(), fname))
    assert os.path.exists(os.path.abspath(backup_dir)), \
        ("\n--%s-- Warning: Directory `%s' does not exist. . ." % (current_time(), fname))
    backup_name = backup_dir + os.sep + os.path.split(fname)[1] + '.yasi.bak~'
    try:
        shutil.copyfile(fname, backup_name)
    except IOError:
        message = "\n--%s-- Warning: Couldn't backup the file `%s' in `%s', check if you have enough permissions. "
        tpl = (current_time(), fname, backup_dir)
        sys.stderr.write(message % tpl)


def md5sum(content):
    """ md5sum(content : str) -> str

    >>> md5sum('Keyboard not found!! Press F1 to continue...')
    'ad98cde09016d2e99a726966a4291acf'

    Returns a checksum to be used to determine whether the file has changed.
    A simple textual comparison can still do the work
    """
    return hashlib.md5(content).hexdigest()


def find_line_ending(string):
    """ find_line_ending(string : str) -> str

    >>> find_line_ending('Elementary my dear Watson. \\r')
    '\\r'

    Find the line ending in the file so that we can try to preserve it.
    """
    if CRLF in string:
        return CRLF
    elif CR in string:
        return CR
    else:
        return LF


def trim(string):
    """ trim(string : str) -> str

    Uses every usefull hack to try and reduce extra whitespace without
    messing with character literals
    """
    # turn '(print(+ 1 1))' to '(print (+ 1 1))'
    string = re.sub(r'''([^\\(\[, {@~`'#^])(\(|\[|{)''', r'\1 \2', string, re.X)
    # turn  ')(' to ') ('
    string = re.sub(r'(\)|\]|})(\[|\(|{)', r'\1 \2', string)
    # Remove any space before closing brackets '(print 12   )' ==> '(print 12)'
    string = re.sub('[ \t]*(\)|\]|})', r'\1', string)
    # remove extra whitespace "(print     'this)" ==> "(print 'this)"
    string = re.sub('[ \t]{2,}', ' ', string)
    # turn ') ) ) ' into '))) '
    string = re.sub(r'(\))[ \t]*(?=(\)))', r'\1', string)
    string = re.sub(r'(\])[ \t]*(?=(\]))', r'\1', string)
    string = re.sub(r'(})[ \t]*(?=(}))', r'\1', string)
    # turn '( ( ( ' into '((( '
    string = re.sub(r'(\()[ \t]*(?=(\())', r'\1', string)
    string = re.sub(r'(\[)[ \t]*(?=(\[))', r'\1', string)
    string = re.sub(r'({)[ \t]*(?=({))', r'\1', string)
    # remove leading whitespace '   print' ==> 'print'
    string = re.sub('^[ \t]*', '', string)
    # Remove space between quote and opening bracket, "' (1 2 3)" ==> "'(1 2 3)"
    string = re.sub("('|`)[ \t]+(\(|\[|{)", r'\1\2', string)
    return string


def find_trim_limit(string, options=None):
    """ find_trim_limit(string : str) -> int

    >>> find_trim_limit(r'(list #\; #\")')
    14
    >>> find_trim_limit(r'(list ; ")')
    6
    >>> find_trim_limit(r'(list " ;)')
    7

    The function attempts to identify upto which point we are supposed to trim
    so that we don't mess with strings or any aligned comments.

    It does this by comparing the positions of semicolons and double
    quotes. It doesn't consider the multiline comment marker. If your
    code uses multiline comments(#| ... |#), you'll have to use --no-compact mode
    """
    opts = parse_options(options)
    # Find position of the first unescaped semi colon
    comment_start = re.search(r'([^\\];)|(^;)', string)
    # Find position of the first unescaped double quote
    string_start = re.search(r'([^\\]")|(^")', string)
    # Assign -1 if there's no match
    limit = string_start.end() if string_start else -1
    comment_start = comment_start.end() if comment_start else -1
    if comment_start != -1:
        # If a semi colon is found, include all the whitespace before it to preserve
        # any aligned comments
        comment_start = re.search('[ \t]*;', string).start() + 1

    if opts.dialect == 'newlisp':
        # Find out which string type comes first(normal, tag or brace strings)
        brace_string_start = string.find('{')
        tag_string_start = string.find('[text]')
        pos_lst = [limit, brace_string_start, tag_string_start]
        pos_lst = [x for x in pos_lst if x != -1]
        if pos_lst:
            limit = min(pos_lst)

    if comment_start != -1 and limit != -1:
        if comment_start < limit:
            # If the semicolon comes before the comma, it means the string has been
            # commented out
            limit = comment_start
    elif comment_start != -1 and limit == -1:
        # If there's a semicolon but no quote, use the semicolon position as the
        # limit
        limit = comment_start
    elif limit == -1:
        # If neither a semicolon nor a double quote has been found, use the length
        # of the string as the limit
        limit = len(string)
    return limit


def is_macro_name(func_name, dialect):
    """ is_macro_name(func_name : str, dialect : str) -> bool

    >>> is_macro_name('yacc:define-parser')
    True

    Tests if a word is a macro using the language's/dialect's convention,
    e.g macros in Lisp usually start with 'def' and 'with' in Scheme. Saves
    the effort of finding all the macros in Lisp/Scheme/Clojure/newLISP and storing
    them in a list.
    """
    if not func_name:
        return False
    if dialect == 'lisp':
        return re.search('^(macro|def|do|with-)', func_name, re.I)
    if dialect == 'scheme':
        return re.search('^(call-|def|with-)', func_name)
    if dialect == 'clojure':
        return re.search('^(def|with)', func_name)
    if dialect == 'newlisp':
        return re.search('^(macro|def)', func_name)
    else:
        return False


def split_preserve(string, sep):
    """ split_preserve(string : str, sep : str)  -> [str]

    >>> split_preserve('''
    "My dear Holmes, " said I, "this is too much. You would certainly
    have been burned, had you lived a few centuries ago.
                ''', '\\n')
    ['\\n',
     '    "My dear Holmes, " said I, "this is too much. You would certainly\\n',
     '    have been burned, had you lived a few centuries ago.\\n',
     '                ']

    Splits the string and sticks the separator back to every string in the list.
    """
    # split the whole string into a list so that you can iterate line by line.
    str_list = string.split(sep)
    if str_list[-1] == '':
        # If you split 'this\nthat\n' you get ['this', 'that', ''] if
        # you add newlines to every string in the list you get
        # ['this\n', 'that\n', '\n']. You've just added
        # another newline at the end of the file.
        del str_list[-1]
        str_list = [x + sep for x in str_list]
    else:
        # ['this', 'that'] will become ['this\n', 'that\n'] when
        # mapped. A newline has been added to the file. We don't want
        # this, so we strip it below.
        str_list     = [x + sep for x in str_list]
        str_list[-1] = str_list[-1].rstrip(sep)
    return str_list


def all_whitespace(string):
    """ all_whitespace(string : str) -> bool

    >>> all_whitespace('      ')
    True

    Returns True if a string has only whitespace.
    """
    return re.search('^[ \t]*(\r|\n|$)', string)


def pad_leading_whitespace(string, zero_level, blist, options=None):
    """ pad_leading_whitespace(string : str, current_level : int, zero_level : int) -> str

    >>> pad_leading_whitespace("(print 'Yello)")
    "         (print 'Yello)"

    Takes a string and indents it using the current indentation level
    and the zero level.
    """
    opts = parse_options(options)
    if opts.compact:
        # if compact mode is on, split the string into two, trim the first
        # position and merge the two portions.
        trim_limit = find_trim_limit(string, opts)
        comment_line = re.search('^[ \t]*;', string, re.M)
        if comment_line and opts.indent_comments:
            trim_limit = comment_line.end()
        substr1 = string[0:trim_limit]
        substr2 = string[trim_limit:]
        substr1 = trim(substr1)
        string = substr1 + substr2
    else:
        # if in nocompact mode, pad with zero_level spaces.
        string = re.sub('^[ \t]+', '', string, count=0, flags=re.M)
        string = ' ' * zero_level + string

    if blist:
        # if there are unclosed blocks, you pad the line with the
        # current indent level minus the zero level that was
        # added earlier
        current_level = blist[-1]['indent_level']
        string = ' ' * (current_level - zero_level) + string
        return string, current_level
    else:
        # Otherwise(all blocks finished), return the string as it is since
        # it's the head of a new block
        return string, 0


def indent_line(zerolevel, bracket_list, line, in_comment, in_symbol_region,
                options=None):
    """ indent_line(zerolevel : int, bracket_list : list, line : str, in_comment : bool,
                    in_symbol_region : bool, options : string|list)

    Most important function in the indentation process. It uses the bracket
    locations stored in the list to indent the line.
    """
    opts = parse_options(options)
    comment_line = re.search('^[ \t]*;', line, re.M)
    if opts.indent_comments:
        # We are allowed to indent comment lines
        comment_line = False
    if not opts.compact and zerolevel == 0 and bracket_list == [] and not in_comment:
        # If nocompact mode is on and there are no unclosed blocks, try to
        # find the zero level by simply counting spaces before a line that
        # is not empty or has a comment
        leading_spaces = re.search('^[ \t]+[^; )\n\r]', line)
        if leading_spaces:
            # NOTE: If you don't subtract one here, the zero level will increase
            # every time you indent the file because the character at the end of
            # the regex is part of the capture.
            zerolevel = leading_spaces.end() - 1

    if in_symbol_region:
        # No processing done in strings and comments
        return zerolevel, line, 0
    elif not comment_line and not all_whitespace(line):
        # If this is not a comment line indent the line.
        # If the list is empty, then the current_level defaults
        # to zero
        curr_line, current_level = pad_leading_whitespace(line, zerolevel,
                                                          bracket_list, opts)
        return zerolevel, curr_line, current_level
    else:
        return zerolevel, line, 0

# ---------------------------------------------------------------------------------
# GLOBAL CONSTANTS::

CR   = '\r'
LF   = '\n'
CRLF = CR + LF

KEYWORD0 = 0  # Non-keyword
KEYWORD1 = 1  # Indents uniformly by 1 unit
KEYWORD2 = 2  # Distinguishes subforms
KEYWORD3 = 3  # Indens uniformly by 2 units

# Keywords that indent by two spaces
SCHEME_KEYWORDS = \
    ['define', 'local-odd?', 'when', 'begin', 'case',
     'local-even?', 'do', 'call-with-bytevector-output-port',
     'call-with-input-file', 'call-with-port',
     'call-with-current-continuation', 'open-file-input-port',
     'call-with-port', 'call-with-values', 'call-with-output-file',
     'call-with-string-output-port', 'define-syntax', 'if', 'let', 'let*',
     'library', 'unless', 'lambda', 'syntax-rules', 'syntax-case',
     'let-syntax', 'letrec*', 'letrec', 'let-values', 'let*-values',
     'with-exception-handler', 'with-input-from-file',
     'with-interrupts-disabled', 'with-input-from-string',
     'with-output-to-file', 'with-input-from-port',
     'with-output-to-string', 'with-source-path', 'with-syntax',
     'with-implicit',
     'with-error-handler', 'module', 'parameterize']

CLOJURE_KEYWORDS = \
    ['defn', 'fn', 'dorun', 'doseq', 'loop', 'when',
     'let', 'defmacro', 'binding', 'doto', 'ns', ':import', 'defstruct',
     'condp', 'comment', 'when', 'when-let', '->', '->>',
     'extend-type', 'reify', 'binding', 'when-not', 'proxy', 'dotimes',
     'try', 'finally', 'for', 'letfn', 'catch', 'iterate', 'while',
     'with-local-vars', 'locking', 'defmulti', 'defmethod', 'extend'
     ]

LISP_KEYWORDS = \
    [':implementation', ':method', 'case', 'defclass',
     'defconstant', 'defgeneric', 'defimplementation',
     'define-condition', 'define-implementation-package',
     'definterface', 'defmacro', 'defmethod', 'defpackage',
     'defproject', 'deftype', 'defun', 'defvar', 'do-external-symbols',
     'dolist', 'dotimes', 'ecase', 'etypecase', 'flet', 'handler-bind',
     'if', 'lambda', 'let', 'let*', 'print-unreadable-object',
     'macrolet', 'defparameter', 'with-slots', 'typecase', 'loop', 'when', 'prog1',
     'unless', 'with-open-file', 'with-output-to-string', 'with-input-from-string',
     'block', 'handler-case', 'defstruct', 'eval-when', 'tagbody', 'ignore-errors',
     'labels', 'multiple-value-bind'
     ]

NEWLISP_KEYWORDS = \
    ['while', 'if', 'case', 'dotimes', 'define', 'dolist', 'catch',
     'throw', 'lambda', 'lambda-macro', 'when', 'unless', 'letex', 'begin',
     'dostring', 'let', 'letn', 'doargs', 'define-macro', 'until', 'do-until',
     'do-while', 'for-all', 'find-all', 'for'
     ]

# The 'if' and 'else' part of an if block should have different indent levels so
# that they can stand out since there's no else Keyword in Lisp/Scheme to make
# this explicit.  list IF_LIKE helps us track these keywords.
IF_LIKE = ['if']


def parse_rc_json():
    """ Reads the json configuration file(.yasirc.json), parses it and returns the
    dictionary
    """
    fname = '.yasirc.json'
    path = os.path.expanduser('~/' + fname)
    if os.path.exists(fname):
        path = os.path.abspath(fname)
    content = ''
    with open(path) as f:
        content = f.read()
    if content:
        return json.loads(content)
    else:
        return {}


def assign_indent_numbers(lst, inum, dic=collections.defaultdict(int)):
    """ Associate keywords with their respective indentation numbers
    """
    for i in lst:
        dic[i] = inum
    return dic


def add_keywords(dialect):
    """ add_keywords(dialect : str) -> [str, str]

    Takens a lisp dialect name and returns a list of keywords that increase
    indentation by two spaces and those that can be one-armed like 'if'
    """
    keywords = collections.defaultdict(int)
    two_spacers = []
    two_armed = IF_LIKE
    if dialect == 'lisp':  # Lisp
        two_spacers = LISP_KEYWORDS
        two_armed += ['multiple-value-bind', 'destructuring-bind', 'do', 'do*']
    elif dialect == 'scheme':  # Scheme
        two_spacers = SCHEME_KEYWORDS
        two_armed += ['with-slots', 'do', 'do*']
    elif dialect == 'clojure':  # Clojure
        two_spacers = CLOJURE_KEYWORDS
        two_armed += []
    elif dialect == 'newlisp':  # newLISP
        two_spacers = NEWLISP_KEYWORDS
        two_armed += []
    elif dialect == 'all':
        two_spacers = LISP_KEYWORDS + SCHEME_KEYWORDS + CLOJURE_KEYWORDS + \
            NEWLISP_KEYWORDS
    keywords = assign_indent_numbers(two_spacers, KEYWORD1, keywords)
    keywords = assign_indent_numbers(two_armed, KEYWORD2, keywords)
    rc_keywords = parse_rc_json()
    keywords.update(rc_keywords[dialect])
    return keywords

# ---------------------------------------------------------------------------------


def find_first_arg_pos(bracket_offset, curr_line, options=None):
    """ find_first_arg_pos(bracket_offset : int, curr_line : str) -> [int, int]

    Arguments:
    bracket_offset - The position of the bracket in the current line e.g
        "    (  list 'timey 'wimey  )" --> 4
        " (  list 'timey 'wimey  )"    --> 1
        "(  list 'timey 'wimey  )"     --> 0

    >>> find_first_arg_pos(0, "(     list 'one-sheep 'two-sheep )")
    [11, 5]

    Returns the position of the first argument to the function relative to the
    position of the opening bracket and the number of spaces between the opening
    bracket and the function name.
    The two values will to be used to align the other arguments in the subsequent line
    """
    opts = parse_options(options)
    spaces_before_func = 0
    subline = curr_line[bracket_offset + 1:]
    if re.search('^[ \t]*($|\r)', subline):
        # whitespace extending to the end of the line means there's no
        # function in this line. The indentation level defaults to one.
        arg_pos = 1
    else:
        if bracket_offset != len(curr_line) - 1 and curr_line[bracket_offset + 1] == ' ':
            # control reaches here if we are not at the end of the line
            # and whitespace follows. We must first find the position of the
            # function and then the arguments position
            match = re.search(' +[^)\]]| \)', subline)  # Find the first non whitespace/bracket character
            if match:
                spaces_before_func = match.end() - match.start() - 1
                end = match.end()
            else:
                end = 0
            # Then use the end of the whitespace group as the first argument
            arg_pos = re.search(' +([^)])|( *(\(|\[))', subline[end:])
            if arg_pos:
                arg_pos = arg_pos.end() + spaces_before_func + 1
            else:
                arg_pos = spaces_before_func + 1
            if re.match('^[ \t]*(#\||;|$|\r)',
                        subline[(end - 1 + subline[end - 1:].find(' ')):]):
                # But, if a comment if found after the function name, the
                # indent level becomes one
                arg_pos = spaces_before_func + opts.default_indent
        else:
            # If there's no space after the bracket, simply find the end of the
            # whitespace group
            match = re.search(' +([^)}\n\r])|( *(\(|\[|{))', subline)
            if match:  # found the argument
                arg_pos = match.end()
            else:  # Either empty list or argument is in the next line
                arg_pos = 1
            if re.match('^[\t ]*(;|$|\r)', subline[subline.find(' '):]):
                # Again if a comment is found after the function name, the
                # indent level defaults to 1
                arg_pos = spaces_before_func + opts.default_indent
    return [arg_pos, spaces_before_func]


def _pop_from_list(bracket, lst, line, real_pos, offset, msg_stack):
    """ _pop_from_list(char : str, lst : [str], line : str,
                        real_pos : int, offset : int)

    The function is called when a closing bracket is encountered. The function
    simply pops the last pushed item and issues a warning if an error is
    encountered.
    """
    # Try to spot a case when a square bracket is used to close a round bracket
    # block
    if bracket == ']':
        correct_closer = '['
    elif bracket == ')':
        correct_closer = '('
    else:
        correct_closer = '{'
    if lst != []:
        popped = lst.pop()
        popped_char = popped['character']
        popped_pos = popped['line_number']
        popped_offset = popped['bracket_pos']
        if popped_char is not correct_closer:
            message = "Bracket `%s' does not match `%s' at (%d, %d)"
            message = message % (bracket, popped_char, popped_pos, popped_offset)
            warning_info = {
                'msg': message,
                'line': line,
                'column': real_pos
            }
            msg_stack.append(warning_info)
    else:
        # If the list is empty and a closing bracket is found, it means we have
        # excess brackets. That warning is issued here. The coordinates used
        # will be slightly or largely off target depending on how much your
        # code was modified when used with compact mode
        message = "Unmatched closing bracket `%s'" % bracket
        warning_info = {
            'msg': message,
            'line': line,
            'column': offset + 1
        }
        msg_stack.append(warning_info)
    return lst


def _push_to_list(lst, func_name, char, line, offset,
                  first_arg_pos, first_item, in_list_literal,
                  lead_spaces, options=None):
    """ _push_to_list(lst : [str], func_name : str, char : str, line : int, offset : int,
                        first_arg_pos :int , first_item : int, in_list_literal : bool,
                        lead_spaces : int, options : str)

    Called when an opening bracket is encountered. A hash containing the
    necessary data to pin point errors and the indentation level is stored in
    the list and the list returned.
    """
    opts = parse_options(options)
    keywords = add_keywords(opts.dialect)
    pos_hash = {'character': char,
                'line_number': line,
                'bracket_pos': offset,
                'indent_level': offset + first_arg_pos,  # the default value, e.g in normal function
                'func_name': func_name,
                'spaces': 0}

    is_macro = is_macro_name(func_name, opts.dialect)
    two_spacer = is_macro or keywords[func_name] == KEYWORD1

    if in_list_literal or char == '{' or (char == '[' and opts.dialect == 'clojure'):
        # found quoted list or clojure hashmap/vector
        pos_hash['indent_level'] = first_item

    elif keywords[func_name] == KEYWORD2:
        # We only make the if-clause stand out if not in uniform mode
        pos_hash['indent_level'] = lead_spaces + ((offset + opts.indent_size * 2)
                                                  if not opts.uniform
                                                  else (offset + opts.indent_size))

    elif two_spacer and func_name != '':
        pos_hash['indent_level'] = lead_spaces + offset + opts.indent_size

    lst.append(pos_hash)
    try:
        # A hack to make flets and labels in Lisp not indent like
        # functions. The 'labels' indentation may not be exactly
        # perfect.
        parent_func = lst[-3]['func_name']
        if parent_func in ['flet', 'labels', 'macrolet']:
            lst[-1]['indent_level'] = offset + opts.indent_size
    except IndexError:
        pass
    return lst


def indent_code(original_code, options=None):
    """ indented_code(string : str, fname : str) -> [...]

    Arguments:
    fpath: Simply used in formatting the warning messages

    >>> indent_code("(print\n'Hello)")
    [(),
     False,
     (),
     [],
     [],
     False,
     0,
     False,
     [],
     (),
     '',
     "(print\n'Hello)",
     "(print\n 'Hello)"]

    The last entry in the list is the indented string.
    """

    opts = parse_options(options)
    keywords = add_keywords(opts.dialect)

    # Safeguards against processing brackets inside strings
    in_string = False

    # newLISP use curly brackets as a syntax for multiline strings
    # this variable here tries to keep track of that
    in_newlisp_string = 0
    in_newlisp_tag_string = False
    newlisp_brace_locations = []
    first_tag_string = ()

    # zero_level helps us get the same results as Sitaram's indenter when in
    # --no-compact mode.
    zero_level = 0

    # The two variables prevent formatting comment regions or symbols with whitespace
    in_comment = 0
    in_symbol_with_space = False
    comment_locations = []
    last_symbol_location = ()

    # A in_symbol_region is the region between pipes(|   |) or in strings. This
    # includes the comment region. This region is not to be messed with.
    in_symbol_region = in_string or in_comment or in_symbol_with_space or \
        in_newlisp_string or in_newlisp_tag_string

    # we need to know the line number in order to issue almost accurate messages about
    # unclosed brackets and string
    line_number = 1

    # Stores the last position a quote was encountered so that in case there are
    # any unclosed strings, we can pinpoint them
    last_quote_location = ()

    line_ending = find_line_ending(original_code)
    code_lines = split_preserve(original_code, line_ending)

    indented_code = ""

    bracket_locations = []

    # List of warnings from errors in the code
    message_stack = []

    for line in code_lines:
        escaped   = False
        curr_line = line

        # Get the indent level and the indented line
        zero_level, curr_line, indent_level = indent_line(zero_level,
                                                          bracket_locations,
                                                          line, in_comment,
                                                          in_symbol_region, opts)
        # Build up the indented string.
        indented_code += curr_line
        offset = 0
        for curr_char in curr_line:
            next_char = curr_line[offset + 1:offset + 2]
            prev_char = curr_line[offset - 1:offset]

            substr = curr_line[offset + 1:]  # slice to the end

            if escaped:
                # Move to the next character if the current one has been escaped
                escaped = False
                offset += 1
                continue

            if curr_char == '\\' and not in_newlisp_string and not in_newlisp_tag_string:
                # the next character has been escaped
                escaped = True

            if curr_char == ';' and not in_symbol_region and not \
                    (prev_char == '#' and opts.dialect == 'scheme'):
                # a comment has been found, go to the next line
                # A sharp sign(#) before a semi-colon in Scheme is used to
                # comment out sections of code. We don't treat it as a comment
                break

            # ----------------------------------------------------------
            # Comments are dealt with here. Clojure and newLISP don't have Lisp
            # style multiline comments so don't include them.
            if opts.dialect not in ['clojure', 'newlisp'] and curr_char == '|' \
                    and not in_string:
                if prev_char == '#' and not in_symbol_with_space:
                    comment_locations.append((line_number, offset))
                    in_comment += 1
                elif in_comment and next_char == '#':
                    in_comment -= 1
                    comment_locations.pop()
                elif not in_comment:
                    if in_symbol_with_space:
                        last_symbol_location = ()
                        in_symbol_with_space = False
                    else:
                        last_symbol_location = (line_number, offset)
                        in_symbol_with_space = True

            # ----------------------------------------------------------

            # Strings are dealt with here only if we are not comment
            if not (in_symbol_with_space or in_comment or in_newlisp_tag_string):
                if curr_char == '"':
                    last_quote_location = (line_number, offset)
                    in_string = True if not in_string else False
                if opts.dialect == 'newlisp' and not in_string:
                    # We handle newLISP's multiline(brace) string here. Brace
                    # strings can nest
                    if curr_char == '{':
                        newlisp_brace_locations.append((line_number, offset))
                        in_newlisp_string += 1
                    elif curr_char == '}':
                        if newlisp_brace_locations:
                            newlisp_brace_locations.pop()
                        else:
                            message = "Attempt to close a non-existent newLISP string"
                            warning_info = {
                                'msg': message,
                                'line': line_number,
                                'column': offset
                            }
                            message_stack.append(warning_info)
                        in_newlisp_string -= 1

            if curr_char == '[' and opts.dialect == 'newlisp' and not \
                    (in_newlisp_string or in_string):
                # We have to handle tag strings in newLISP here.
                if re.match('\[text\]', curr_line[offset:offset + 7]):
                    in_newlisp_tag_string = True
                    if first_tag_string == ():
                        first_tag_string = (line_number, offset)
                elif re.match('\[/text\]', curr_line[offset:offset + 7]):
                    in_newlisp_tag_string = False
                    first_tag_string = ()

            in_symbol_region = in_string or in_comment or in_symbol_with_space \
                or in_newlisp_string or in_newlisp_tag_string

            if in_symbol_region:
                # move on if we are in a string, a symbol with a space or a comment
                # altogether known as the symbol region
                offset += 1
                continue

            # Finds the real position of a bracket to be used in pinpointing where
            # the unclosed bracket is. The real position is different from the offset
            # because current offset is the position of the bracket in the
            # trimmed string not the original.
            real_position = (offset - zero_level) + \
                len(re.findall('^[ \t]*', line)[0]) - indent_level
            if curr_char in ['(', '[', '{']:
                if curr_char in ['[', '{'] and opts.dialect in ['lisp', 'newlisp']:
                    # Square/Curly brackets are used should not contribute to
                    # the indentation in CL and newLISP
                    offset += 1
                    continue

                first_arg_pos, spaces_before_func = \
                    find_first_arg_pos(offset, curr_line, opts)
                func_name = substr[0:first_arg_pos - 1].strip(')]\t\n\r ').lower()
                in_list_literal = False
                if re.search("('|`|#)([ \t]*\(|\[)($|\r)", curr_line[0:offset + 1]):
                    in_list_literal = True

                if re.search('^[^ \t]+[ \t]*($|\r)', substr):
                    # The function is the last symbol/form in the line
                    func_name = substr.strip(')]\t\n\r ').lower()
                if in_list_literal:
                    # an empty string is always in a non-empty string, we don't want
                    # this. We set False as the func_name because it's not a string
                    # in_list_literal prevents an keyword in a list literal from
                    # affecting the indentation
                    func_name = ''

                if func_name in ['define-macro', 'defmacro']:
                    # Macro names are part of two space indenters.
                    # This part tries to find the name so that it is not indented
                    # like a function the next time it's used.
                    end_of_space = re.search('^[ \t]*', substr).end()
                    substr = substr[end_of_space:]
                    substr = substr[re.search('[ \t]*', substr).start():].strip()
                    macro_name = substr[:substr.find(' ')]  # macro name is delimeted by whitespace
                    if macro_name != '':
                        keywords[macro_name] = KEYWORD1

                # first_item stores the position of the first item in the literal list
                # it's necessary so that we don't assume that the first item is always
                # after the opening bracket.
                first_item = re.search('[ \t]*', curr_line[offset + 1:]).end() + offset + 1
                bracket_locations = _push_to_list(bracket_locations[:], func_name,
                                                  curr_char, line_number, offset,
                                                  first_arg_pos, first_item,
                                                  in_list_literal,
                                                  spaces_before_func, opts)

            elif curr_char in [']', ')', '}']:
                if curr_char in [']', '}'] and opts.dialect in ['lisp', 'newlisp']:
                    # Square/Curly brackets are used should not contribute to
                    # the indentation in CL and newLISP
                    offset += 1
                    continue

                bracket_locations = _pop_from_list(curr_char, bracket_locations[:],
                                                   line_number, real_position,
                                                   offset, message_stack)

            if bracket_locations and curr_char in [' ', '\t'] and \
                    keywords[bracket_locations[-1]['func_name']] == KEYWORD2:
                # This part changes the indentation level of a then clause so that
                # we can achieve something like:
                #         (if (= this that)
                #             'then-form
                #           'else-form)
                # This is done by keeping track of the number of spaces found. If
                # you find two spaces it means that, for example that we have just
                # passed the then-form and hence should decrease the indentation
                # level by 2.(I shamelessly copied this algorithm from Dorai's
                # indenter)
                if prev_char not in [' ', '\t', ''] or not \
                        re.search('^[ \t]*(;|#\||$|\r)', curr_line):
                    # The level shouldn't be decreased if the line is a comment
                    # line. The regex above takes care of that.
                    bracket_locations[-1]['spaces'] += 1
                if bracket_locations[-1]['spaces'] == 2:
                    bracket_locations[-1]['indent_level'] -= \
                        0 if opts.uniform else opts.indent_size
                    # some dummy value to prevent control from reaching here again
                    bracket_locations[-1]['spaces'] = 999

            offset += 1
        line_number += 1
    return [message_stack, first_tag_string, in_newlisp_tag_string, last_symbol_location, comment_locations,
            newlisp_brace_locations, in_string, in_comment,
            in_symbol_with_space, bracket_locations,
            last_quote_location, original_code, indented_code]


def _after_indentation(indentation_state, options=None, fpath=''):
    """ _after_indentation(indentation_state : lst):

    Called after the string has been indented appropriately.
    It takes care of writing the file and checking for unclosed strings
    or comments.
    """
    # Receive all the state variables. *This is the price you for modularity*
    message_stack, first_tag_string, in_newlisp_tag_string, last_symbol_location, comment_locations, \
        newlisp_brace_locations, in_string, _, _, \
        bracket_locations, last_quote_location, original_code, indented_code \
        = indentation_state

    fname = os.path.basename(fpath)
    opts = parse_options(options)

    for msg in message_stack:
        if opts.warning:
            if opts.files:
                msg['fname'] = fname
                sys.stderr.write('{fname}:{line}:{column}: {msg}'.format(**msg))
            else:
                # Input was passed through stdin
                sys.stderr.write(':{line}:{column}: {msg}'.format(**msg))

    if bracket_locations:
        # If the bracket_locations list is not empty it means that there are some
        # brackets(opening) that haven't been closed.
        for bracket in bracket_locations:
            line = bracket['line_number']
            column = bracket['bracket_pos']
            character = bracket['character']
            # The bracket_locations are not very accurate. The warning might be
            # misleading because it considers round and square brackets to be
            # the same.
            message = "\n%s:%d:%d: Unmatched `%s'"
            if opts.warning:
                sys.stderr.write(message % (fname, line, column, character))

    if newlisp_brace_locations:
        for brace in newlisp_brace_locations:
            message = "\n%s:%d:%d: Unclosed newLISP brace string"
            if opts.warning:
                sys.stderr.write(message % (fname, brace[0], brace[1]))

    if comment_locations:
        for comment in comment_locations:
            message = "\n%s:%d:%d: Unclosed multiline comment"
            tpl = (fname,) + comment
            if opts.warning:
                sys.stderr.write(message % tpl)

    if last_symbol_location:
        message = "\n%s:%d:%d: Unclosed symbol"
        tpl = (fname,) + last_symbol_location
        if opts.warning:
            sys.stderr.write(message % tpl)

    if in_string:
        message = "\n%s:%d:%d: String extends to end-of-file"
        tpl = (fname,) + last_quote_location
        if opts.warning:
            sys.stderr.write(message % tpl)

    if in_newlisp_tag_string:
        message = "\n%s:%d:%d: Tag string extends to end-of-file"
        tpl = (fname,) + first_tag_string
        if opts.warning:
            sys.stderr.write(message % tpl)

    output_file = opts.output_file
    if not output_file:
        output_file = fpath

    if indented_code == original_code and opts.files:
        message = "\nFile `%s' has already been formatted. Leaving it unchanged. . .\n"
        sys.stderr.write(message % fname)
        if output_file != fpath:
            with open(output_file, 'wb') as indented_file:
                indented_file.write(indented_code.encode('utf8'))
    else:
        if opts.output:
            print(indented_code, end='')

        if opts.modify:
            # write in binary mode to preserve the original line ending
            with open(output_file, 'wb') as indented_file:
                indented_file.write(indented_code.encode('utf8'))


def indent_files(arguments=sys.argv[1:]):
    """ indent_files(fname : str)

    1. Creates a backup of the source file(backup_source_file())
    2. Reads the files contents(read_file())
    3. Indents the code(indent_code())
    4. Writes the file or print the indented code(_after_indentation())
    """
    opts = parse_options(arguments)
    if not opts.files:
        # Indent from stdin
        code = sys.stdin.read()
        indent_result = indent_code(code, opts)
        _after_indentation(indent_result)

    for fname in opts.files:
        code = read_file(fname)
        if not opts.dialect:
            # Guess dialect from the file extensions if none is specified in the
            # command line
            if fname.endswith('.lisp'):
                opts.dialect = 'lisp'
            elif fname.endswith('.lsp'):
                opts.dialect = 'newlisp'
            elif fname.endswith('.clj'):
                opts.dialect = 'clojure'
            elif fname.endswith('.ss') or fname.endswith('.scm'):
                opts.dialect = 'scheme'
        indent_result = indent_code(code, opts)
        _after_indentation(indent_result, fpath=fname)

        if opts.backup:
            # Create a backup file in the directory specified
            backup_source_file(fname, opts)


def main():
    """ Entry point """
    indent_files()

if __name__ == '__main__':
    main()
