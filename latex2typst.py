import re

GREEK = {
 'alpha':'alpha','beta':'beta','gamma':'gamma','delta':'delta','epsilon':'epsilon.alt',
 'varepsilon':'epsilon','zeta':'zeta','eta':'eta','theta':'theta','vartheta':'theta.alt',
 'iota':'iota','kappa':'kappa','lambda':'lambda','mu':'mu','nu':'nu','xi':'xi','pi':'pi',
 'varpi':'pi.alt','rho':'rho','varrho':'rho.alt','sigma':'sigma','varsigma':'sigma.alt',
 'tau':'tau','upsilon':'upsilon','phi':'phi','varphi':'phi.alt','chi':'chi','psi':'psi',
 'omega':'omega',
 'Gamma':'Gamma','Delta':'Delta','Theta':'Theta','Lambda':'Lambda','Xi':'Xi','Pi':'Pi',
 'Sigma':'Sigma','Upsilon':'Upsilon','Phi':'Phi','Psi':'Psi','Omega':'Omega',
}

SYMBOL_MAP = {
 'circ':'degree', 'cdot':'dot.op', 'times':'times', 'pm':'plus.minus', 'mp':'minus.plus',
 'leq':'<=', 'le':'<=', 'geq':'>=', 'ge':'>=', 'neq':'!=', 'ne':'!=', 'approx':'approx',
 'equiv':'equiv', 'sim':'tilde.op', 'cong':'tilde.equiv',
 'in':'in', 'notin':'in.not', 'ni':'in.rev', 'subset':'subset', 'subseteq':'subset.eq',
 'supset':'supset', 'cup':'union', 'cap':'inter', 'setminus':'without', 'backslash':'without',
 'infty':'infinity', 'emptyset':'nothing', 'varnothing':'nothing',
 'rightarrow':'->', 'to':'->', 'Rightarrow':'=>', 'leftrightarrow':'<->',
 'Leftrightarrow':'<=>', 'longrightarrow':'-->', 'mapsto':'|->',
 'forall':'forall', 'exists':'exists', 'nexists':'exists.not',
 'partial':'diff', 'nabla':'nabla', 'perp':'perp', 'parallel':'parallel',
 'angle':'angle', 'triangle':'triangle', 'square':'square',
 'wedge':'and', 'vee':'or', 'lnot':'not', 'neg':'not',
 'cdots':'dots.h.c', 'ldots':'dots.h', 'dots':'dots.h', 'vdots':'dots.v', 'ddots':'dots.down',
 'ast':'ast', 'star':'star.op', 'div':'div.op',
 'lbrack':'[', 'rbrack':']', 'langle':'angle.l', 'rangle':'angle.r',
 'lceil':'ceil.l', 'rceil':'ceil.r', 'lfloor':'floor.l', 'rfloor':'floor.r', 'vert':'|',
 # Big operators: the LaTeX command name does NOT always match Typst's own
 # symbol name (e.g. "\int" -> Typst's symbol is called "integral", not
 # "int"), so a mismatch here falls through to being emitted as a bare,
 # unquoted word and Typst errors with "unknown variable: <name>" at
 # compile time. Map every one explicitly instead of relying on luck.
 'int':'integral', 'iint':'integral.double', 'iiint':'integral.triple', 'oint':'integral.cont',
 'sum':'sum', 'prod':'product', 'coprod':'product.co',
 'bigcup':'union.big', 'bigcap':'inter.big', 'bigvee':'or.big', 'bigwedge':'and.big',
 'bigoplus':'plus.circle.big', 'bigotimes':'times.circle.big', 'bigsqcup':'union.sq.big',
 'bmod':'mod', 'pmod':'mod',
 'colon':':',
 'mid':'divides', 'lvert':'|', 'rvert':'|',
}

KNOWN_OPS = {'cos','sin','tan','cot','sec','csc','lim','log','ln','min','max','det','exp',
             'mod','sup','inf','gcd','lcm','arg',
             'arcsin','arccos','arctan','sinh','cosh','tanh','coth'}

# Bare words Typst's math mode already knows how to display without being
# quoted -- Greek-letter names (Capital-first ones included, e.g. "Gamma",
# "Sigma") and the function names this converter itself emits (frac(...),
# sqrt(...), cal(...), etc.). Anything else that looks like a multi-letter
# identifier (not a single-letter variable) needs to be quoted, or Typst
# reads it as a variable-name lookup and errors with "unknown variable".
_SAFE_BARE_IDENTS = set(GREEK.values()) | {
    'frac', 'sqrt', 'root', 'cases', 'bold', 'hat', 'overline', 'underline',
    'arrow', 'display', 'cal', 'bb', 'upright', 'op',
}

# Operators whose "under-label" (x -> 2, n -> infinity, x in D, ...) is
# conventionally typeset centered *below* the operator name rather than as a
# plain corner subscript. Typst only does this automatically in display-style
# equations; inline math (the usual case here, since formulas sit inside a
# sentence) falls back to a corner subscript, which looks wrong. We wrap just
# the "op_(...)" piece in display(...) so it renders the display-style way
# even inline, without blowing up the size of the rest of the formula.
LIMIT_STYLE_OPS = {'lim', 'max', 'min', 'sup', 'inf'}
_TRAILING_LIMIT_OP_RE = re.compile(
    r'(?:^|(?<=[^A-Za-z0-9]))(' + '|'.join(sorted(LIMIT_STYLE_OPS, key=len, reverse=True)) + r')\s*$'
)

MATH_WORDS = [
    'khi và chỉ khi',
    'nếu và chỉ nếu',
    'với mọi',
    'tồn tại',
    'ngược lại',
    'trong đó',
    'đáp số',
    'đáp án',
    'khi',
    'nếu',
    'với',
    'thì',
    'và',
    'hoặc',
    'tại',
    'mọi',
    'khác',
]


def _fix_glued_words(s):
    for w in sorted(MATH_WORDS, key=len, reverse=True):
        s = re.sub(r'\b' + re.escape(w) + r'(?=[a-zA-Z0-9\\])', w + ' ', s, flags=re.IGNORECASE)
        s = re.sub(r'(?<=[a-zA-Z0-9])' + re.escape(w) + r'\b', ' ' + w, s, flags=re.IGNORECASE)
    return s


def _wrap_math_words(s):
    for w in sorted(MATH_WORDS, key=len, reverse=True):
        pattern = r'(?<![\\a-zA-Z0-9_])' + re.escape(w) + r'(?![a-zA-Z0-9_])'
        def _sub_word(m):
            start = m.start()
            prefix = s[:start]
            if prefix.count('"') % 2 == 1:
                return m.group(0)
            last_text = prefix.rfind(r'\text{')
            if last_text != -1:
                after_text = prefix[last_text:]
                if after_text.count('{') > after_text.count('}'):
                    return m.group(0)
            return f'\\text{{{m.group(0)}}}'
        s = re.sub(pattern, _sub_word, s, flags=re.IGNORECASE)
    return s


def _split_top_level(s, sep=','):
    parts, depth, cur = [], 0, ''
    for ch in s:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ''
        else:
            cur += ch
    parts.append(cur)
    return parts


_ALIGNED_RE = re.compile(
    r'(?:\\left\s*(?P<ld>\\\{|\\lbrack|\[|\()\s*)?'
    r'\\begin\{aligned\}(?P<body>.*?)\\end\{aligned\}'
    r'(?:\s*\\right\s*(?P<rd>\.|\\\}|\\rbrack|\]|\)))?',
    re.DOTALL)


def _convert_condition(cond):
    cond = cond.strip()
    cond = _fix_glued_words(cond)
    cond = _wrap_math_words(cond)
    cond_t = latex_to_typst(cond)
    if not cond_t.startswith('"') and not any(op in cond_t for op in ('<', '>', '=', '!', 'in', '+', '-', '*', '/')):
        if re.search(r'[a-zA-Z\u00C0-\u024F\u1EA0-\u1EF9]', cond_t):
            cond_t = f'"{cond_t}"'
    return cond_t


def _convert_aligned(m):
    ld = m.group('ld')
    body = m.group('body')
    rows = re.split(r'\\\\', body)
    pieces = []
    for row in rows:
        row = row.strip()
        row = re.sub(r'^&', '', row).strip()
        if not row:
            continue
        if ',' in row:
            cells = _split_top_level(row, ',')
        elif '&' in row:
            cells = _split_top_level(row, '&')
        else:
            cells = [row]
        expr = latex_to_typst(cells[0])
        if len(cells) > 1:
            cond = ','.join(cells[1:]).strip()
            cond_t = _convert_condition(cond)
            pieces.append(f'{expr} & {cond_t}')
        else:
            pieces.append(expr)
    delim_kw = ''
    if ld in ('\\lbrack', '['):
        delim_kw = 'delim: "["'
    elif ld == '(':
        delim_kw = 'delim: "("'
    args = ', '.join(([delim_kw] if delim_kw else []) + pieces)
    return 'display(cases(' + args + '))'


TOKEN_RE = re.compile(r"""
    (?P<cmd>\\[a-zA-Z]+) |
    (?P<esc>\\.) |
    (?P<open>\{) |
    (?P<close>\}) |
    (?P<car>\^) |
    (?P<sub>_) |
    (?P<amp>&) |
    (?P<nl>\\\\) |
    (?P<ws>\s+) |
    (?P<ch>.)
""", re.VERBOSE | re.DOTALL)


def tokenize(s):
    toks = []
    for m in TOKEN_RE.finditer(s):
        kind = m.lastgroup
        val = m.group()
        toks.append((kind, val))
    return toks



def _wrap1(fn, a):
    """Build `fn(a)` for a Typst function that takes exactly one required
    content argument (bold, overline, hat, sqrt, ...). If `a` came out empty
    or whitespace-only -- e.g. from LaTeX like `\\mathbf{ }` (bold applied to
    a bare space) -- calling `fn()` with no argument is a hard Typst error
    ("missing argument: body"), so just drop the wrapper entirely instead.
    """
    if a is None or a.strip() == '':
        return ''
    return f'{fn}({a})'


def _frac(a, b):
    """`frac(a, b)` needs BOTH slots filled -- `frac(, b)` or `frac(a, )` is
    a Typst syntax error (dangling comma), not just an empty-content error.
    If one side is empty, just return the other side; if both are, return
    nothing rather than emit invalid syntax."""
    a_ok = a is not None and a.strip() != ''
    b_ok = b is not None and b.strip() != ''
    if a_ok and b_ok:
        return f'frac({a}, {b})'
    if a_ok:
        return a
    if b_ok:
        return b
    return ''


class Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def next(self):
        t = self.peek()
        self.i += 1
        return t

    def skip_ws(self):
        while self.peek()[0] == 'ws':
            self.next()

    def parse_group_or_atom(self):
        self.skip_ws()
        kind, val = self.peek()
        if kind == 'open':
            self.next()
            inner = self.parse_seq(stop_on_close=True)
            if self.peek()[0] == 'close':
                self.next()
            return inner
        return self.parse_one_unit()

    def parse_one_unit(self):
        kind, val = self.next()
        if kind is None:
            return ''
        if kind == 'ws':
            return ' '
        if kind == 'cmd':
            return self.dispatch(val[1:])
        if kind == 'esc':
            c = val[1]
            if c in '{}':
                return '\\' + c
            if c in ',;:!':
                return ' '
            if c == ' ':
                return ' '
            if c == '\\':
                return '\n'
            return c
        if kind == 'nl':
            return '\n'
        if kind == 'open':
            inner = self.parse_seq(stop_on_close=True)
            if self.peek()[0] == 'close':
                self.next()
            return inner
        if kind == 'close':
            return ''
        if kind in ('car', 'sub', 'amp'):
            return val
        return val

    def dispatch(self, name):
        if name == 'frac':
            a = self.parse_group_or_atom()
            b = self.parse_group_or_atom()
            return _frac(a, b)
        if name == 'sqrt':
            self.skip_ws()
            if self.peek() == ('ch', '['):
                self.next()
                idx = ''
                while self.peek()[0] is not None and self.peek() != ('ch', ']'):
                    idx += self.parse_one_unit()
                if self.peek() == ('ch', ']'):
                    self.next()
                a = self.parse_group_or_atom()
                return f'root({idx}, {a})'
            a = self.parse_group_or_atom()
            return f'sqrt({a})'
        if name in ('text', 'mathrm', 'operatorname', 'textrm'):
            a = self.parse_group_or_atom()
            a = a.strip()
            if a in KNOWN_OPS:
                return ' ' + a + ' '
            if a == '':
                return ''
            if a == 'd':
                # \mathrm{d}x -- the upright differential "d" in an integral,
                # almost always typed glued straight to the variable with no
                # following space (same root cause as the bare "dx" fix
                # above, just arriving via \mathrm instead of plain text).
                return '"d" '
            return f'"{a}"'
        if name == 'mathbb':
            a = self.parse_group_or_atom().strip()
            m = re.match(r'^(in|in\.not)\s+(.*)$', a)
            if m:
                return f' {m.group(1)} bb({m.group(2)})'
            return f'bb({a})'
        if name == 'mathcal':
            a = self.parse_group_or_atom()
            return _wrap1('cal', a)
        if name in ('mathbf', 'boldsymbol', 'bf'):
            a = self.parse_group_or_atom()
            return _wrap1('bold', a)
        if name in ('overrightarrow', 'vec'):
            a = self.parse_group_or_atom()
            return _wrap1('arrow', a)
        if name == 'overleftarrow':
            a = self.parse_group_or_atom()
            return _wrap1('arrow.l', a)
        if name in ('widehat', 'hat'):
            a = self.parse_group_or_atom()
            return _wrap1('hat', a)
        if name in ('overline', 'bar'):
            a = self.parse_group_or_atom()
            return _wrap1('overline', a)
        if name == 'overset':
            top = self.parse_group_or_atom()
            base = self.parse_group_or_atom()
            if base is None or base.strip() == '':
                return ''
            if top is None or top.strip() == '':
                return base
            return f'overset({base}, {top})'
        if name == 'directedarc':
            # Directed arc ("cung lượng giác"): curved arrow drawn over the
            # name. cung() is defined in render.py's Typst preamble.
            a = self.parse_group_or_atom()
            if a is None or a.strip() == '':
                return ''
            # Plain point/letter names ("AM", "A'B") go in quotes -- as upright
            # text it stays one tight word ("AM"), instead of being split
            # into spaced italic letters ("A M") by the point-name handling.
            if re.fullmatch(r"[A-Za-z0-9']+", a.strip()):
                return f'cung("{a.strip()}")'
            return f'cung({a})'
        if name in ('overparen', 'wideparen', 'overarc'):
            # Plain arc ("cung tròn", no arrow): same wide arc Typst draws for
            # \widehat -- which is exactly how the Word original shows it.
            a = self.parse_group_or_atom()
            if a is None or a.strip() == '':
                return ''
            return f'overarc({a})'
        if name == 'underline':
            a = self.parse_group_or_atom()
            return _wrap1('underline', a)
        if name in ('left', 'right'):
            self.skip_ws()
            kind, val = self.peek()
            if kind == 'esc' and val in ('\\{', '\\}'):
                self.next()
                return val
            if kind == 'cmd' and val[1:] in SYMBOL_MAP:
                self.next()
                return ' ' + SYMBOL_MAP[val[1:]] + ' '
            if kind == 'ch' and val == '.':
                self.next()
                return ''
            if kind == 'ch' and val in '()[]|':
                self.next()
                return val
            return ''
        if name == 'begin':
            env = self.parse_group_or_atom()
            return self.handle_generic_env(env)
        if name in KNOWN_OPS:
            return ' ' + name + ' '
        if name in GREEK:
            return ' ' + GREEK[name] + ' '
        if name in SYMBOL_MAP:
            return ' ' + SYMBOL_MAP[name] + ' '
        if name == 'not':
            nxt = self.parse_one_unit()
            return nxt + '.not'
        if name in ('quad', 'qquad'):
            return '  '
        if name in ('displaystyle', 'nonumber', 'notag', 'limits', 'nolimits'):
            return ''
        # Unknown LaTeX command with no Typst mapping on file. Emitting it as
        # a bare word is what caused past crashes ("unknown variable: int",
        # "unknown variable: Oxyz") -- Typst only accepts a bare word if it
        # happens to already be one of ITS OWN symbol names, and LaTeX/Typst
        # names frequently don't match. Fall back to quoted text instead: one
        # formula shows the wrong glyph (the literal command name) instead of
        # the whole PDF failing to build.
        return f'"{name}"'

    def handle_generic_env(self, env):
        cur = ''
        rows = []
        while True:
            kind, val = self.peek()
            if kind is None:
                break
            if kind == 'cmd' and val[1:] == 'end':
                self.next()
                self.parse_group_or_atom()
                break
            if kind == 'nl':
                self.next()
                rows.append(cur)
                cur = ''
                continue
            cur += self.parse_one_unit()
        rows.append(cur)
        rows = [re.sub(r'^&\s*', '', r.strip()).strip() for r in rows if r.strip()]
        return 'cases(' + ', '.join(rows) + ')'

    def parse_seq(self, stop_on_close=False):
        out = ''
        while True:
            kind, val = self.peek()
            if kind is None:
                break
            if stop_on_close and kind == 'close':
                break
            if kind == 'car':
                self.next()
                arg = self.parse_group_or_atom()
                if arg.strip() == '0' and out and out[-1].isdigit():
                    # A bare superscript "0" directly on a NUMBER (e.g.
                    # "54^0") is essentially always someone using a digit "0"
                    # as a crude stand-in for the degree sign -- real angle
                    # values are always numbers, never a variable. Require a
                    # digit base specifically so a genuine exponent identity
                    # like "x^0=1" is left alone (same reasoning as the
                    # identical fix for MathType/OLE formulas in
                    # mtef2latex.py, which covers the same typing habit in
                    # MathType rather than Word's own equation editor).
                    out += '^(degree)'
                    continue
                out += f'^({arg})'
                continue
            if kind == 'sub':
                self.next()
                arg = self.parse_group_or_atom()
                m = _TRAILING_LIMIT_OP_RE.search(out)
                if m:
                    out = out[:m.start(1)] + f'display({m.group(1)}_({arg}))'
                else:
                    out += f'_({arg})'
                continue
            if kind == 'cmd':
                self.next()
                result = self.dispatch(val[1:])
                # A command's dispatch result can start right off with a
                # bare word (e.g. \overparen -> "accent(...)", \sqrt ->
                # "sqrt(...)"). If whatever precedes it in `out` ends in a
                # letter/digit with no space of its own ("sđ\overset{...}"
                # glued with no space in the source, same as "x\sqrt{...}"),
                # the two runs together read as ONE identifier to Typst.
                # Insert the missing separator here, at the actual point of
                # concatenation, instead of trying to reverse-engineer word
                # boundaries after the fact in post-processing.
                if result and out and out[-1].isalnum() and result[0].isalpha():
                    out += ' '
                out += result
                continue
            out += self.parse_one_unit()
        return out


def latex_to_typst(latex):
    if latex is None:
        return ''
    latex = latex.strip()
    # Dấu nháy kép THẲNG (") gõ trong công thức (vd: P:"∃x∈ℝ, (x-2)^2<0") là dấu trích
    # dẫn cần HIỂN THỊ, nhưng trong Typst cặp " " bắt đầu một chuỗi chữ thường -> cả đoạn
    # công thức bên trong bị in nguyên như văn bản ("exists x in ℝ, (x-2)^(2)<0").
    # Đổi lần lượt thành dấu nháy cong mở “ / đóng ” trước khi chuyển đổi.
    if '"' in latex:
        _qn = [0]

        def _curl(_m):
            _qn[0] += 1
            return '\u201c' if _qn[0] % 2 else '\u201d'
        latex = re.sub(r'"', _curl, latex)
    # a dangling trailing "\ " (explicit-space command) becomes an unmatched
    # backslash once the trailing space is stripped away; drop it outright.
    latex = re.sub(r'\\+\s*$', '', latex).strip()
    if latex == '':
        return ''

    # Word's native Equation Editor (not MathType) encodes a typed degree
    # symbol as a DOUBLY-nested superscript -- pandoc's OMML->LaTeX export
    # faithfully reproduces it as e.g. "30^{{^\circ}}" (an outer superscript
    # whose content is itself a braced, superscripted "\circ") instead of
    # the simple "30^{\circ}" every other degree symbol in these files uses.
    # Collapse that one specific pandoc quirk before tokenizing, or it parses
    # as a superscript-of-a-superscript ("^(^(degree))" in the Typst output).
    latex = re.sub(r'\^\{\{\^\\circ\}\}', r'^{\\circ}', latex)
    # Cùng một lỗi mã hóa độ ở dạng khác: ^{^\circ}, ^{^{\circ}}, ^{{}^\circ}
    latex = re.sub(r'\^\{\s*(?:\{\s*\})?\s*\^\s*\{?\s*\\circ\s*\}?\s*\}', r'^{\\circ}', latex)

    # "Arc measure" notation ("sđ AM" with a curved arrow drawn over "AM")
    # arrives via a DIFFERENT OMML encoding than \overparen -- Word's own
    # equation editor builds it as \overset{\curvearrowright}{AM} (stack a
    # right-curving-arrow symbol on top of "AM") instead of a single accent
    # template. Same visual meaning, so reuse the already-correct \overparen
    # handling rather than needing a separate code path for it.
    latex = re.sub(r'\\overset\{\\curvearrow(?:right|left)\}\{([^{}]*)\}', r'\\directedarc{\1}', latex)

    # Solid-geometry apex.base naming ("S.ABCD", "H.ABC") uses a bare period
    # between bare letters; a literal "." in Typst math is field-access syntax,
    # so swap it for a safe placeholder before tokenizing.
    latex = re.sub(r'(?<=[A-Z])\.(?=[A-Z]{2,})', ' @@DOTC@@ ', latex)
    # bare "//" (parallel-lines notation, typed literally rather than via \parallel)
    latex = re.sub(r'/{2,}', ' @@PARALLEL@@ ', latex)

    placeholders = {}

    def _stash(m):
        key = f'@@P{len(placeholders)}@@'
        placeholders[key] = _convert_aligned(m)
        return key

    latex2 = _ALIGNED_RE.sub(_stash, latex)
    latex2 = _fix_glued_words(latex2)
    latex2 = _wrap_math_words(latex2)

    toks = tokenize(latex2)
    p = Parser(toks)
    result = p.parse_seq()

    for key, val in placeholders.items():
        result = result.replace(key, val)

    result = re.sub(r'[ \t]+', ' ', result).strip()
    result = re.sub(r'\n\s*\n+', '\n', result)
    result = result.replace('@@DOTC@@', 'dot.c')
    result = result.replace('@@PARALLEL@@', 'parallel')
    # Typst reads a bare multi-letter run as a single identifier lookup (unlike
    # LaTeX's automatic per-letter italics), so a geometry point-set label like
    # "ABCD" or "SAB" must be quoted as literal text to avoid an unknown-variable error.
    # Runs of capitals ("AB", "ABCD", "SABC") are point/segment names: show them
    # as separate italic letters (as in the Word original) rather than quoted
    # upright text.
    result = re.sub(r'(?<![A-Za-z0-9"])[A-Z]{2,}(?![A-Za-z0-9])', lambda m: ' '.join(m.group(0)), result)
    # Same problem for a mixed-case run like "Oxyz", "Oxy" (coordinate-plane /
    # axis names are the common case in Vietnamese math text) -- Typst still
    # reads that as a bare identifier lookup. Quote it too, except for the
    # handful of words Typst already recognizes on its own (Greek letter
    # names, this converter's own function names).
    def _quote_mixed_case(m):
        word = m.group(0)
        if word in _SAFE_BARE_IDENTS:
            return word
        # Tia / truc toa do: Ox, Oy, Oz, Oxy, Oxyz, va ten tia O + 1 chu thuong
        # bat ky (Ou, Ov, Ot, Oa, ...) -> hien thi nhu chu in nghieng roi: O u, O v
        if re.fullmatch(r'O[xyz]{1,3}|O[a-z]', word):
            return ' '.join(word)
        return f'"{word}"'
    result = re.sub(r'(?<![A-Za-z0-9"])[A-Z][a-z]+(?![A-Za-z0-9(])', _quote_mixed_case, result)
    # A single-letter variable directly glued to a numeral ("k2pi", "k180")
    # would otherwise be read by Typst as one identifier; split them apart.
    result = re.sub(r'(?<![A-Za-z0-9])([a-zA-Z])(\d)', r'\1 \2', result)
    # Calculus differential notation ("dx", "dy", "dt", ...) commonly comes
    # out of OMML with the "d" glued straight onto the variable letter, with
    # no space -- e.g. "f(x)dx". That is the exact same "bare multi-letter
    # identifier" problem as "Oxyz"/"int" above (Typst reads glued "dx" as
    # one unknown variable), just for a pattern the earlier two passes don't
    # catch since it's lowercase-only and only 2 letters. Insert a space so
    # it becomes two separate, auto-recognized single-letter symbols.
    result = re.sub(r'(?<![A-Za-z0-9])d([a-zA-Z])(?![A-Za-z0-9])', r'd \1', result)
    # General safety net for the same class of bug ("ax", "xy", "abc", ...):
    # Typst reads ANY bare run of 2+ letters as ONE identifier lookup and fails
    # with "unknown variable" unless it is a name Typst itself knows. So split
    # every such run into single letters (which Typst accepts as plain
    # variables), except words we know are real Typst names/functions/symbols,
    # anything followed by "(" or "." (function calls / dotted symbol names),
    # and anything inside a quoted string.
    return _split_unknown_words(result)


_TYPST_KNOWN_WORDS = None


def _typst_known_words():
    global _TYPST_KNOWN_WORDS
    if _TYPST_KNOWN_WORDS is None:
        words = set(KNOWN_OPS) | set(_SAFE_BARE_IDENTS) | set(GREEK.values())
        for v in SYMBOL_MAP.values():
            for part in re.findall(r'[A-Za-z]+', v):
                words.add(part)
        words |= {
            'sum', 'product', 'integral', 'union', 'inter', 'nothing', 'infinity',
            'degree', 'plus', 'minus', 'times', 'div', 'dif', 'diff', 'dots',
            'in', 'not', 'and', 'or', 'forall', 'exists', 'without', 'approx',
            'equiv', 'subset', 'supset', 'perp', 'parallel', 'angle', 'triangle',
            'square', 'nabla', 'star', 'ast', 'dot', 'delim', 'mod', 'lim', 'det',
            'gcd', 'lcm', 'arg', 'sup', 'inf', 'max', 'min', 'log', 'exp', 'ln',
            'sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'sinh', 'cosh', 'tanh', 'coth',
            'arcsin', 'arccos', 'arctan', 'mid', 'tilde', 'vec', 'norm', 'abs',
            'floor', 'ceil', 'binom', 'mat', 'accent', 'attach', 'limits', 'scripts',
            'italic', 'upright', 'sans', 'serif', 'mono', 'frak', 'cal', 'bb',
            'op', 'lr', 'sqrt', 'root', 'frac', 'cases', 'hat', 'bold', 'display', 'cung', 'overarc',
            'inline', 'script', 'sscript', 'arrow', 'overline', 'underline',
            'overbrace', 'underbrace', 'bar', 'thin', 'med', 'thick', 'quad',
            'wide', 'zws', 'true', 'false', 'none', 'auto',
        }
        _TYPST_KNOWN_WORDS = words
    return _TYPST_KNOWN_WORDS


# Function-like Typst names that are normally immediately followed by "(" --
# used to split a bare VARIABLE glued straight onto a following function call
# with no space, e.g. "x\sqrt{x-1}" (no space in the source) currently
# produces "xsqrt(x-1)" -- one bare word immediately before "(" was always
# left untouched on the assumption it must be a real function/symbol name,
# but that assumption breaks when it's actually "<glued variable><real
# function>". Checked as a SUFFIX of the glued word, longest first, so e.g.
# "msin" splits into "m" + "sin" rather than matching something shorter.
_CALLABLE_SUFFIXES = tuple(sorted({
    'sqrt', 'frac', 'root', 'cases', 'bold', 'hat', 'overline', 'underline',
    'arrow', 'cal', 'bb', 'mat', 'binom', 'abs', 'norm', 'floor', 'ceil',
    'display', 'upright', 'sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'sinh',
    'cosh', 'tanh', 'coth', 'arcsin', 'arccos', 'arctan', 'lim', 'log', 'ln',
    'exp', 'det', 'gcd', 'lcm', 'arg', 'sup', 'inf', 'max', 'min', 'mod',
    'integral', 'sum', 'product', 'union', 'inter',
}, key=len, reverse=True))


_SPLIT_OPS = tuple(sorted(
    ['arcsin', 'arccos', 'arctan', 'sinh', 'cosh', 'tanh', 'coth',
     'sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'log', 'ln', 'lim'],
    key=len, reverse=True))


def _split_letters_with_ops(word):
    """Tach 1 cum chu dinh lien thanh cac bien don le, nhung GIU NGUYEN ten ham
    luong giac/log (MathType luu 'cosx' thanh c,o,s,x -> phai ra 'cos x',
    khong phai 'c o s x' vi se hien thanh 3 chu in nghieng roi rac)."""
    out, i = [], 0
    while i < len(word):
        for op in _SPLIT_OPS:
            if word.startswith(op, i):
                out.append(op)
                i += len(op)
                break
        else:
            out.append(word[i])
            i += 1
    return ' '.join(out)


def _split_unknown_words(text):
    known = _typst_known_words()
    pieces = re.split(r'("(?:[^"\\]|\\.)*")', text)
    for i, piece in enumerate(pieces):
        if piece.startswith('"') and piece.endswith('"') and len(piece) >= 2:
            continue

        def fix_ascii_word(word, nxt):
            """word is ASCII-only (2+ letters). nxt is whatever single
            character follows it in the surrounding text (possibly '' if
            word runs to the very end of its piece)."""
            if nxt == '(':
                if word in known:
                    return word
                for suf in _CALLABLE_SUFFIXES:
                    if word.endswith(suf) and len(word) > len(suf):
                        prefix = word[:-len(suf)]
                        prefix_out = prefix if len(prefix) == 1 else ' '.join(prefix)
                        return prefix_out + ' ' + suf
                return word
            if word in ('nu', 'mu', 'xi') and nxt in ('_', '^'):
                # "nu_(1)" dinh lien, khong co khoang trang = tich n.u_1 (MathType
                # luu tung ky tu). Chu cai Hy Lap that (\\nu) luon di kem dau cach
                # sau no nen khong roi vao nhanh nay.
                return ' '.join(word)
            if word in known:
                # A known bare word (e.g. "cos") glued straight onto a
                # following digit or letter with no space -- "cos54",
                # "cos2a" -- is the exact same gluing problem as "Oxyz"/"dx"
                # fixed above, just with the glue being a recognized name
                # instead of an unknown one, so it slips past the checks
                # above (which only fire for '(' or an UNrecognized word).
                # Typst still reads "cos54" as one unknown identifier either
                # way; insert the missing space.
                if nxt and nxt.isalnum():
                    return word + ' '
                return word
            # No exception for a trailing "." or ":" here -- an unrecognized
            # glued word like "sinb" (from MathType's plain per-character
            # "s","i","n","b" content, not a \sin command) must still be
            # split into letters even when a period follows right after it
            # ("...+sinb.cosa"), or Typst reads the whole glued run as one
            # unknown identifier regardless of what comes next.
            return _split_letters_with_ops(word)

        def fix(m):
            word = m.group(0)
            end = m.end()
            nxt = piece[end:end + 1]
            if word.isascii():
                return fix_ascii_word(word, nxt)
            # Contains at least one non-ASCII (Vietnamese) letter -- a plain
            # Vietnamese word/abbreviation ("sđ" for "số đo", an arc-measure
            # label) needs quoting as text, not ASCII-style letter-splitting.
            # (The case where this used to glue straight onto a dispatched
            # command's output with no space -- "sđ\overset{...}" ->
            # "sđaccent(...)" -- is now prevented at the source, in
            # parse_seq's command dispatch, so `word` here is just the
            # Vietnamese text on its own.)
            return word if word in known else f'"{word}"'

        # No "." in the lookbehind: a glued word right after a literal period
        # ("sinb.cosa" -> the "cosa" half) still needs to be checked and
        # split/spaced like any other, same reasoning as dropping the "."
        # exception in fix() above. Matches any Unicode letter run (not just
        # ASCII A-Za-z) so a Vietnamese word/abbreviation written directly in
        # math mode is caught too -- see the non-ASCII branch in fix().
        pieces[i] = re.sub(r'(?<![^\W\d_])[^\W\d_]{2,}(?![^\W\d_])', fix, piece)
        # Số thập phân kiểu Việt Nam "3,5": dấu phẩy ở giữa 2 nhóm chữ số (và không
        # phải dãy 1,2,3). Typst coi "," trong frac(3,5, 3) là dấu ngăn tham số
        # (-> lỗi "unexpected argument") và ngoài hàm thì in thành "3, 5" có cách.
        # class("normal", ",") là dấu phẩy không chèn khoảng cách -> "3,5".
        pieces[i] = re.sub(r'(?<![\w.,])(\d+),(\d+)(?!\d|,\d)',
                           r'\1class("normal", ",")\2', pieces[i])
    return ''.join(pieces)


if __name__ == '__main__':
    tests = [
        r'30^{\circ}',
        r'\alpha + k180{^\circ}\left( k\mathbb{\in Z} \right)',
        r'\alpha + k360{^\circ}\left( k \in \mathbb{Z} \right)',
        r'x = \pi + k2\pi',
        r'x = \frac{\pi}{2} + k\pi',
        r'\text{cos}x = - 1',
        r'\text{cos}(\alpha + \beta) = \text{cos}\alpha\text{cos}\beta - \text{sin}\alpha\text{sin}\beta',
        r'\left( u_{n} \right)',
        r'u_{1} = 2',
        r'\frac{1}{10^{103}}',
        r'\left\lbrack \begin{aligned} & x = \frac{\pi}{6} + k2\pi \\ & x = - \frac{\pi}{6} + k2\pi \end{aligned} \right.\ \left( k \in \mathbb{Z} \right)',
        r'f(x) = \left\{ \begin{aligned} & \frac{\sqrt{x + 3} - 2}{x - 1},khix > 1 \\ & - x^{2} + m,khix \leq 1 \end{aligned} \right.\ ',
        r'\lim_{x \rightarrow 2}\left( 3x^{2} + 7x + 11 \right)',
        r'\lbrack 9;11)',
        r'I = \lim_{x \rightarrow 2}\frac{x^{2} - 5x + 6}{x - 2}',
        r'\frac{SK}{SA} = \frac{1}{4}',
        r'u_{n} = \frac{3n}{n^{2} + 2}',
        r'{{u}_{n}}=5n+1.',
        r'{{u}_{n}}',
        r'[20 ; 40)',
        r'S.ABCD',
        r'MN//(ABD)',
    ]
    for t in tests:
        try:
            print('OK ', repr(t), '->', latex_to_typst(t))
        except Exception as e:
            print('ERR', repr(t), '->', e)