"""
Decode MathType's binary MTEF equation format (the format used by "pure"
MathType objects -- i.e. ones MathType did NOT also save with an embedded
"TeX Input Language" translator string, so extract_ole_math()'s simple
marker search finds nothing) into a LaTeX string, which is then fed through
the existing, already-tested latex_to_typst() so it benefits from every fix
already made there (bare-identifier quoting, dx/dy spacing, etc.) instead of
duplicating that logic.

MTEF is Design Science's own binary format; Microsoft/Design Science never
published an official spec. This implementation follows the community
reverse-engineered MTEF v5 spec (docs.wiris.com / rtf2latex2e.sourceforge.net,
originally Design Science's own SDK docs, archived via the Wayback Machine),
matched byte-for-byte against that spec's own worked example (the quadratic
formula) during development, and further checked against real oleObject.bin
streams pulled out of an actual exam .docx.

This only needs to support what actually shows up in typed high-school /
exam-style math: characters, fractions, roots, sub/superscripts, sums,
products, integrals, limits, over/under-bars, arrows/hats/tildes, fences
(parentheses/brackets/braces/bars), and simple systems of
equations (matrix with 1 column -> cases). Anything genuinely unrecognised
degrades to plain concatenated text rather than raising, so a single exotic
construct doesn't take down the object list around it -- but a hard failure
(corrupt/truncated stream) DOES raise, and the caller (extract_ole_math) must
treat that as "could not read this equation" rather than silently emitting
something wrong, since a wrong formula on an exam is worse than a missing one.
"""

TEMPLATE_FENCES = {
    0: ('\\langle ', '\\rangle '),
    1: ('(', ')'),
    2: ('\\{', '\\}'),
    3: ('[', ']'),
    4: ('|', '|'),
    5: ('\\Vert ', '\\Vert '),
    6: ('\\lfloor ', '\\rfloor '),
    7: ('\\lceil ', '\\rceil '),
    8: ('', ''),
    9: ('(', ')'),
}

BIGOP_SYMBOLS = {
    15: '\\int', 16: '\\sum', 17: '\\prod', 18: '\\coprod',
    19: '\\bigcup', 20: '\\bigcap', 21: '\\int', 22: '\\sum',
}

EMBELL_FMT = {
    2: '\\dot{{{0}}}', 3: '\\ddot{{{0}}}', 4: '\\dddot{{{0}}}',
    5: "{0}'", 6: "{0}''", 7: "'{0}", 18: "{0}'''",
    8: '\\tilde{{{0}}}', 9: '\\hat{{{0}}}', 10: '\\not{{{0}}}',
    11: '\\overrightarrow{{{0}}}', 12: '\\overleftarrow{{{0}}}', 13: '\\overleftrightarrow{{{0}}}',
    17: '\\overline{{{0}}}', 29: '\\underline{{{0}}}',
    19: '\\overset{{\\frown}}{{{0}}}', 20: '\\overset{{\\smile}}{{{0}}}',
}


# MTCode is a superset of Unicode, so most characters are just chr(code).
# But the downstream converter (latex_to_typst) understands LaTeX commands
# for math symbols, so translate the common non-ASCII ones to those instead
# of leaning on raw Unicode passthrough.
_GREEK_LC = 'alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho varsigma sigma tau upsilon phi chi psi omega'.split()
_GREEK_UC = {0x393: 'Gamma', 0x394: 'Delta', 0x398: 'Theta', 0x39B: 'Lambda', 0x39E: 'Xi',
             0x3A0: 'Pi', 0x3A3: 'Sigma', 0x3A5: 'Upsilon', 0x3A6: 'Phi', 0x3A8: 'Psi', 0x3A9: 'Omega'}
UNICODE_TO_LATEX = {
    # A literal backslash CHARACTER typed as equation content (used as the
    # "set minus" notation, e.g. "ℝ \ {2018}") must NOT go through the
    # generic escaper below: escaping "\" there produces "\\", which is
    # LaTeX's OWN line-break command, not a literal backslash -- silently
    # inserting a real newline into the middle of the formula. Route it
    # through the \backslash command name instead so it dispatches the same
    # way as the rest of the "without" (set-minus) family.
    0x5C: '\\backslash ',
    0x2223: '\\mid ', 0x2212: '-', 0x00D7: '\\times ', 0x00B1: '\\pm ', 0x2213: '\\mp ',
    0x00F7: '\\div ', 0x221E: '\\infty ', 0x2264: '\\leq ', 0x2265: '\\geq ',
    0x2260: '\\neq ', 0x2248: '\\approx ', 0x2261: '\\equiv ', 0x2208: '\\in ',
    0x2209: '\\notin ', 0x222A: '\\cup ', 0x2229: '\\cap ', 0x2282: '\\subset ',
    0x2286: '\\subseteq ', 0x2283: '\\supset ', 0x2192: '\\rightarrow ',
    0x21D2: '\\Rightarrow ', 0x21D4: '\\Leftrightarrow ', 0x2194: '\\leftrightarrow ',
    0x2200: '\\forall ', 0x2203: '\\exists ', 0x2205: '\\emptyset ', 0x00B0: '^{\\circ}',
    0x2220: '\\angle ', 0x22A5: '\\perp ', 0x2225: '\\parallel ', 0x2202: '\\partial ',
    0x2207: '\\nabla ', 0x2026: '\\ldots ', 0x22C5: '\\cdot ', 0x2022: '\\cdot ',
    0x2211: '\\sum ', 0x220F: '\\prod ', 0x222B: '\\int ', 0x221A: '\\surd ',
    0x2032: "'", 0x2033: "''", 0x00A0: ' ', 0x2009: ' ', 0x2002: ' ', 0x2003: ' ',
}
for _i, _n in enumerate(_GREEK_LC):
    UNICODE_TO_LATEX[0x3B1 + _i] = '\\' + _n + ' '
for _c, _n in _GREEK_UC.items():
    UNICODE_TO_LATEX[_c] = '\\' + _n + ' '
UNICODE_TO_LATEX.pop(0x3BF, None)  # omicron has no LaTeX command; fall back to 'o'
UNICODE_TO_LATEX[0x3BF] = 'o'

_ESCAPE_CHARS = set('\\{}_^&%$#')


def _escape_char(ch):
    return ('\\' + ch) if ch in _ESCAPE_CHARS else ch


class MTEFError(Exception):
    pass


class MTEFParser:
    def __init__(self, data):
        self.d = data
        self.p = 0

    # ---- low-level readers, per the MTEF v5 spec ----
    def u8(self):
        if self.p >= len(self.d):
            raise MTEFError('unexpected end of MTEF stream')
        b = self.d[self.p]
        self.p += 1
        return b

    def peek8(self):
        if self.p >= len(self.d):
            return None
        return self.d[self.p]

    def eof(self):
        return self.p >= len(self.d)

    def u16(self):
        lo = self.u8()
        hi = self.u8()
        return lo | (hi << 8)

    def signed(self):
        b = self.u8()
        if b == 255:
            lo = self.u8()
            hi = self.u8()
            return (lo | (hi << 8)) - 32768
        return b - 128

    def unsigned(self):
        b = self.u8()
        if b == 255:
            lo = self.u8()
            hi = self.u8()
            return lo | (hi << 8)
        return b

    def cstr(self):
        start = self.p
        end = self.d.find(b'\x00', start)
        if end == -1:
            raise MTEFError('unterminated string in MTEF stream')
        s = self.d[start:end].decode('latin-1', 'replace')
        self.p = end + 1
        return s

    def skip_nudge(self):
        b1 = self.u8()
        b2 = self.u8()
        if b1 == 128 and b2 == 128:
            self.p += 4  # dx,dy as 16-bit values

    # ---- header ----
    def read_header(self):
        self.p += 5  # version, platform, product, prodVersion, prodSubVersion
        self.cstr()  # application key, e.g. "DSMT7"
        self.u8()    # equation options

    # ---- definition records (consumed for stream-position correctness;
    # their content doesn't affect the LaTeX we emit) ----
    def read_font_style_def(self):
        self.unsigned()
        self.u8()

    def read_size_record(self):
        b = self.u8()
        if b == 101:
            self.u16()
        elif b == 100:
            self.u8()
            self.u16()
        # else: single-byte dsize already consumed as `b`

    def read_color(self):
        self.unsigned()

    def read_color_def(self):
        opt = self.u8()
        n = 4 if (opt & 0x01) else 3
        for _ in range(n):
            self.u16()
        if opt & 0x04:
            self.cstr()

    def read_font_def(self):
        self.unsigned()
        self.cstr()

    def read_encoding_def(self):
        self.cstr()

    def read_eqn_prefs(self):
        self.u8()  # options
        for _ in range(2):  # sizes array, spaces array
            count = self.u8()
            nibbles = count * 1  # count is byte-count of dims, not nibble count directly used below
            # Each array: 1 byte count-of-dimensions, then a nibble stream; we
            # don't need the values, just to skip correctly. Each dimension is
            # a units nibble + digit nibbles terminated by 0xF, so instead of
            # tracking dimension boundaries we just scan nibble-by-nibble
            # until we've consumed `count` terminator (0xF) nibbles.
            self.p -= 0
            terms_needed = count
            terms_seen = 0
            nibble_hi = True
            cur_byte = 0
            while terms_seen < terms_needed:
                if nibble_hi:
                    cur_byte = self.u8()
                    nib = (cur_byte >> 4) & 0xF
                else:
                    nib = cur_byte & 0xF
                nibble_hi = not nibble_hi
                if nib == 0xF:
                    terms_seen += 1
            if not nibble_hi:
                pass  # mid-byte; byte already consumed, fine
        style_count = self.u8()
        for _ in range(style_count):
            idx = self.unsigned()
            if idx != 0:
                self.u8()

    def read_ruler_body(self):
        n = self.u8()
        for _ in range(n):
            self.u8()
            self.u16()

    # ---- MTCode -> character ----
    @staticmethod
    def mtcode_to_char(mtcode):
        if mtcode is None:
            return ''
        if mtcode in UNICODE_TO_LATEX:
            return UNICODE_TO_LATEX[mtcode]
        # MathType uses codepoints in the Unicode Private Use Area (U+E000-
        # U+F8FF) for its OWN internal glyphs that have no real Unicode
        # meaning -- most commonly a manually-inserted space from its
        # spacing palette (observed in real files as e.g. U+EF02). None of
        # these exist in any real font, so passing one straight through as
        # chr(mtcode) renders as a "tofu" box (sometimes shown with a dot)
        # in the PDF. Treat any of them as a plain space rather than guess
        # further -- a slightly-off space is harmless; an unrenderable glyph
        # in the middle of an exam formula is not.
        if 0xE000 <= mtcode <= 0xF8FF:
            return ' '
        try:
            return chr(mtcode)
        except ValueError:
            return ''

    # ---- object lists ----
    def read_object_list(self):
        items = []
        while True:
            if self.eof():
                raise MTEFError('object list ran past end of stream without END')
            tag = self.u8()
            if tag == 0:
                break
            if tag == 6:  # EMBELL modifies the previous CHAR in this same list
                wrap = self.read_embell_body()
                if items and items[-1][0] == 'CHAR':
                    items[-1] = ('CHAR', wrap(items[-1][1]))
                continue
            node = self.read_record(tag)
            if node is not None:
                items.append(node)
        return items

    def read_record(self, tag):
        if tag == 1:
            return ('LINE', self.read_line_body())
        if tag == 2:
            return ('CHAR', self.read_char_body())
        if tag == 3:
            return ('TMPL', self.read_tmpl_body())
        if tag == 4:
            return ('PILE', self.read_pile_body())
        if tag == 5:
            return ('MATRIX', self.read_matrix_body())
        if tag == 7:
            self.read_ruler_body()
            return None
        if tag == 8:
            self.read_font_style_def()
            return None
        if tag == 9:
            self.read_size_record()
            return None
        if 10 <= tag <= 14:
            return None
        if tag == 15:
            self.read_color()
            return None
        if tag == 16:
            self.read_color_def()
            return None
        if tag == 17:
            self.read_font_def()
            return None
        if tag == 18:
            self.read_eqn_prefs()
            return None
        if tag == 19:
            self.read_encoding_def()
            return None
        if tag >= 100:
            n = self.unsigned()
            self.p += n
            return None
        raise MTEFError(f'unknown MTEF record tag {tag}')

    def read_line_body(self):
        opt = self.u8()
        if opt & 0x08:
            self.skip_nudge()
        if opt & 0x04:
            self.u16()
        if opt & 0x02:
            t = self.u8()
            if t == 7:
                self.read_ruler_body()
        if opt & 0x01:
            return ''
        items = self.read_object_list()
        return self.combine_items(items)

    def read_char_body(self):
        opt = self.u8()
        if opt & 0x08:
            self.skip_nudge()
        self.signed()  # typeface -- not needed for the character itself
        mtcode = None
        if not (opt & 0x20):
            mtcode = self.u16()
        if opt & 0x04:
            self.u8()
        if opt & 0x10:
            self.u16()
        raw_ch = self.mtcode_to_char(mtcode)
        ch = raw_ch if (mtcode in UNICODE_TO_LATEX) else _escape_char(raw_ch)
        if opt & 0x01:
            # mtefOPT_CHAR_EMBELL: an embellishment LIST is embedded right
            # here, inside the CHAR record's own bytes (not as a separate
            # top-level object-list entry) -- a sequence of EMBELL(6) records
            # terminated by END(0), same as any other object list. Skipping
            # this (as an earlier version of this parser did) silently
            # desyncs every byte read after it, corrupting the rest of the
            # equation without raising -- confirmed against a real exam file
            # where it truncated "P(\overline{B})" straight after the 'B'.
            while True:
                tag = self.u8()
                if tag == 0:
                    break
                if tag != 6:
                    raise MTEFError(f'expected EMBELL(6) in char embellishment list, got {tag}')
                wrap = self.read_embell_body()
                ch = wrap(ch)
        return ch

    def read_embell_body(self):
        opt = self.u8()
        if opt & 0x08:
            self.skip_nudge()
        etype = self.u8()
        fmt = EMBELL_FMT.get(etype, '{0}')
        return lambda s, fmt=fmt: fmt.format(s)

    def read_tmpl_body(self):
        opt = self.u8()
        if opt & 0x08:
            self.skip_nudge()
        selector = self.u8()
        v1 = self.u8()
        if v1 & 0x80:
            v2 = self.u8()
            variation = (v1 & 0x7F) | (v2 << 8)
        else:
            variation = v1
        self.u8()  # template-specific options
        items = self.read_object_list()
        return self.render_template(selector, variation, items)

    def read_pile_body(self):
        opt = self.u8()
        if opt & 0x08:
            self.skip_nudge()
        self.u8()  # halign
        self.u8()  # valign
        if opt & 0x02:
            t = self.u8()
            if t == 7:
                self.read_ruler_body()
        items = self.read_object_list()
        return [v for k, v in items if k == 'LINE']

    def read_matrix_body(self):
        opt = self.u8()
        if opt & 0x08:
            self.skip_nudge()
        self.u8(); self.u8(); self.u8()  # valign, h_just, v_just
        rows = self.unsigned()
        cols = self.unsigned()
        n_row_parts = rows + 1
        n_col_parts = cols + 1
        self.p += (n_row_parts * 2 + 7) // 8
        self.p += (n_col_parts * 2 + 7) // 8
        items = self.read_object_list()
        lines = [v for k, v in items if k == 'LINE']
        return (rows, cols, lines)

    # ---- combine an object list into one LaTeX fragment ----
    def combine_items(self, items):
        parts = []
        for kind, val in items:
            if kind in ('CHAR', 'TMPL'):
                parts.append(val)
            elif kind == 'PILE':
                parts.append(self.render_pile(val))
            elif kind == 'MATRIX':
                parts.append(self.render_matrix(val))
            elif kind == 'LINE':
                parts.append(val)
        return ''.join(parts)

    def render_pile(self, lines):
        lines = [l for l in lines if l != '']
        if not lines:
            return ''
        if len(lines) == 1:
            return lines[0]
        return '\\begin{aligned}' + ' \\\\ '.join(lines) + '\\end{aligned}'

    def render_matrix(self, mrc):
        rows, cols, lines = mrc
        lines = list(lines)
        while len(lines) < rows * cols:
            lines.append('')
        if cols == 1:
            body = [lines[r] for r in range(rows)]
            return '\\begin{cases}' + ' \\\\ '.join(body) + '\\end{cases}'
        row_strs = []
        for r in range(rows):
            row_cells = lines[r * cols:(r + 1) * cols]
            row_strs.append(' & '.join(row_cells))
        return '\\begin{pmatrix}' + ' \\\\ '.join(row_strs) + '\\end{pmatrix}'

    def render_template(self, selector, variation, items):
        # MathType can put a multi-line PILE (or a MATRIX) directly in a
        # template's slot -- e.g. the "{" fence around a piecewise function
        # wraps a PILE of its branches with no intervening LINE record.
        # Treat those the same as a LINE slot (render them to their string
        # form right away) so L() below finds them; otherwise a fence's main
        # slot silently comes out empty even though the PILE itself decoded
        # fine (confirmed against a real piecewise-function formula).
        norm_items = []
        for k, v in items:
            if k == 'PILE':
                norm_items.append(('LINE', self.render_pile(v)))
            elif k == 'MATRIX':
                norm_items.append(('LINE', self.render_matrix(v)))
            else:
                norm_items.append((k, v))
        items = norm_items
        lines = [v for k, v in items if k == 'LINE']
        chars = [v for k, v in items if k == 'CHAR']

        def L(i):
            return lines[i] if i < len(lines) else ''

        if 0 <= selector <= 9:
            main = L(0)
            # The fence glyphs ALSO arrive as explicit CHAR subobjects here,
            # but MathType encodes them via its own internal "MT Extra" font
            # using Private Use Area codepoints that have no real Unicode
            # meaning (confirmed against real files: a "|...|" absolute-value
            # fence's two CHAR objects decode to literal PUA codepoints with
            # no standard glyph, which the PUA-is-probably-a-space fallback
            # above then turns into blank spaces -- silently erasing the
            # bars). The selector alone already tells us exactly which fence
            # was chosen, so just trust TEMPLATE_FENCES and ignore the
            # explicit chars entirely instead of letting unreliable PUA
            # glyphs override a known-correct default.
            lf, rf = TEMPLATE_FENCES.get(selector, ('(', ')'))
            # `variation` cho biết ngoặc nào thật sự có: bit 0 (0x1) = chỉ có ngoặc TRÁI
            # (vd hệ "[" / "{" chỉ có dấu mở, hay thanh "|" trong {x | ...}), bit 1 (0x2) = chỉ
            # có ngoặc PHẢI, 0x3 = đủ hai bên. Trước đây luôn in đủ hai bên nên bị dư ngoặc.
            if selector != 9:
                if variation == 0x1:
                    rf = '.'
                elif variation == 0x2:
                    lf = '.'
            return f'\\left{lf}{main}\\right{rf}'

        if selector == 10:  # ROOT
            radicand = L(0)
            index = L(1)
            if index.strip():
                return f'\\sqrt[{index}]{{{radicand}}}'
            return f'\\sqrt{{{radicand}}}'

        if selector == 11:  # FRACT
            return f'\\frac{{{L(0)}}}{{{L(1)}}}'

        if selector in (12, 13):  # UBAR / OBAR
            return (f'\\underline{{{L(0)}}}' if selector == 12 else f'\\overline{{{L(0)}}}')

        if selector == 14:  # ARROW
            return f'\\overrightarrow{{{L(0)}}}'

        if 15 <= selector <= 22:  # integrals, sums, products, unions...
            main, lower, upper = L(0), L(1), L(2)
            op = BIGOP_SYMBOLS.get(selector, '\\sum')
            if selector == 15:
                n = variation & 0x3
                if n == 2:
                    op = '\\iint'
                elif n == 3:
                    op = '\\iiint'
            s = op
            if lower.strip():
                s += f'_{{{lower}}}'
            if upper.strip():
                s += f'^{{{upper}}}'
            return s + ' ' + main

        if selector == 23:  # LIM
            main, lower = L(0), L(1)
            s = '\\lim'
            if lower.strip():
                s += f'_{{{lower}}}'
            return s + ' ' + main

        if selector in (24, 25):  # horizontal brace/bracket
            return L(0)

        if selector == 26:  # long division -- rare, best effort
            return L(0) + ' \\div ' + L(1)

        if selector in (27, 28, 29):  # SUB, SUP, SUBSUP
            sub, sup = L(0), L(1)
            if sup.strip() == '0':
                # A bare superscript "0" with nothing else in it -- as in
                # "54^0" -- is essentially never a real exponent in an exam
                # formula (raising to the power 0 is mathematically trivial,
                # so no one writes a trig/algebra question around it).
                # Overwhelmingly, it's someone typing a digit "0" as a crude
                # stand-in for the degree sign because they didn't know how
                # to insert the real ° symbol. Render it as the degree
                # symbol, same as a properly-inserted \circ elsewhere in the
                # same document would.
                sup = '\\circ'
            s = ''
            if sub.strip():
                s += f'_{{{sub}}}'
            if sup.strip():
                s += f'^{{{sup}}}'
            return s

        if selector == 30:  # Dirac bra-ket -- rare, best effort
            return '\\langle ' + L(0) + '|' + L(1) + '\\rangle '

        if selector == 31:  # VEC
            return f'\\vec{{{L(0)}}}'
        if selector == 32:  # TILDE
            return f'\\tilde{{{L(0)}}}'
        if selector == 33:  # HAT
            return f'\\hat{{{L(0)}}}'
        if selector == 34:  # ARC
            return f'\\overparen{{{L(0)}}}'

        # Anything else (Dirac, strike-through, boxes, ...): best-effort
        # fallback so one unusual construct doesn't take down the whole
        # equation -- just concatenate whatever content we did collect.
        return ''.join(lines) if lines else ''.join(chars)


def mtef_to_latex(stream):
    """stream: raw bytes of the 'Equation Native' OLE stream (the MTEF
    header + byte stream; the caller has already stripped any preceding
    OLE-wrapper header such as EQNOLEFILEHDR). Returns a LaTeX string.
    Raises MTEFError on anything unparseable -- the caller must NOT swallow
    that into a best-effort guess; an unreadable formula must fall back to
    "couldn't read this", never to a silently wrong formula."""
    p = MTEFParser(stream)
    p.read_header()
    # Per the spec, the top-level stream is: prefs/defs, initial SIZE record,
    # then a single PILE or LINE record, then a final END. We just keep
    # reading top-level records (using the same object-list reader, which
    # naturally stops at the top-level END) and use whichever LINE/PILE we
    # find as the equation content.
    items = p.read_object_list()
    lines = [v for k, v in items if k == 'LINE']
    piles = [v for k, v in items if k == 'PILE']
    if lines:
        return lines[0]
    if piles:
        return p.render_pile(piles[0])
    # No LINE/PILE at all (shouldn't normally happen) -- fall back to
    # whatever CHAR/TMPL content was collected directly at top level.
    return p.combine_items(items)