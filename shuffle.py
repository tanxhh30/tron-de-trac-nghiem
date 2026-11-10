import random

PART1_LETTERS = ['A', 'B', 'C', 'D']
PART2_LETTERS = ['a', 'b', 'c', 'd']


def _resolve_count(spec, rng, pool_len):
    """spec can be:
      - None               -> use every question in the pool (old behaviour)
      - an int N           -> use exactly N questions (clamped to pool_len)
      - a (min, max) tuple -> pick a random N in that inclusive range for
        THIS variant (so different mã đề end up with different câu counts),
        clamped to pool_len
    Returns an int, or None (meaning "use all").
    """
    if spec is None:
        return None
    if isinstance(spec, (tuple, list)):
        lo, hi = spec
        lo = max(0, min(lo, pool_len))
        hi = max(0, min(hi, pool_len))
        if hi < lo:
            lo, hi = hi, lo
        return rng.randint(lo, hi)
    return max(0, min(int(spec), pool_len))


def _select(pool, n, rng, shuffle_questions):
    """Pick `n` questions out of `pool` (or all of them if n is None).
    When n is given, the n questions are always a RANDOM subset (sampled
    without replacement) regardless of shuffle_questions -- shuffle_questions
    only controls whether the chosen questions are then reordered or kept in
    their original relative order."""
    indexed = list(enumerate(pool))
    if n is not None and n < len(indexed):
        indexed = rng.sample(indexed, n)
    if shuffle_questions:
        rng.shuffle(indexed)
    else:
        indexed.sort(key=lambda t: t[0])
    return [q for _, q in indexed]


def make_variant(questions, seed, shuffle_questions=True, shuffle_options=True, counts=None):
    """questions: flat list of question dicts (from extract_docx.parse_docx).
    counts: optional dict {1: spec1, 2: spec2, 3: spec3, 4: spec4 (tự luận)} controlling how many
      questions of each part this variant draws from the question bank (see
      _resolve_count for what `spec` can be). A missing/None entry means
      "use every question available in that part", same as before.
    Returns (variant, answer_key). Each returned question has fresh
    sequential numbering within its part and, for part1/part2, options
    re-lettered A-D / a-d in the shuffled order.
    """
    rng = random.Random(seed)
    counts = counts or {}
    by_part = {1: [], 2: [], 3: []}
    for q in questions:
        by_part.setdefault(q['part'], []).append(q)

    out = {'part1': [], 'part2': [], 'part3': []}
    answer_key = {'part1': {}, 'part2': {}, 'part3': {}}

    out['essay'] = []

    n1 = _resolve_count(counts.get(1), rng, len(by_part[1]))
    order1 = _select(by_part[1], n1, rng, shuffle_questions)
    for i, q in enumerate(order1, 1):
        opts = q['options'][:]
        if shuffle_options:
            rng.shuffle(opts)
        new_opts = []
        correct_letter = None
        for letter, o in zip(PART1_LETTERS, opts):
            new_opts.append({'label': letter, 'content': o['content'], 'correct': o['correct']})
            if o['correct']:
                correct_letter = letter
        out['part1'].append({'num': i, 'stem': q['stem'], 'images': q['images'], 'options': new_opts})
        answer_key['part1'][i] = correct_letter

    n2 = _resolve_count(counts.get(2), rng, len(by_part[2]))
    order2 = _select(by_part[2], n2, rng, shuffle_questions)
    for i, q in enumerate(order2, 1):
        opts = q['options'][:]
        if shuffle_options:
            rng.shuffle(opts)
        new_opts = []
        flags = {}
        for letter, o in zip(PART2_LETTERS, opts):
            new_opts.append({'label': letter, 'content': o['content'], 'correct': o['correct']})
            flags[letter] = o['correct']
        out['part2'].append({'num': i, 'stem': q['stem'], 'images': q['images'], 'options': new_opts})
        answer_key['part2'][i] = flags

    n3 = _resolve_count(counts.get(3), rng, len(by_part[3]))
    order3 = _select(by_part[3], n3, rng, shuffle_questions)
    for i, q in enumerate(order3, 1):
        out['part3'].append({'num': i, 'stem': q['stem'], 'images': q['images'], 'answer': q['answer']})
        answer_key['part3'][i] = q['answer']

    # Phần 4 -- Tự luận: bốc ngẫu nhiên số câu theo counts[4] (giống Phần 1-3),
    # trộn thứ tự nếu shuffle_questions, đánh số lại từ 1. (Đặt sau cùng để không
    # làm đổi kết quả trộn của Phần 1-3 với cùng seed.)
    essays = by_part.get('essay', [])
    n4 = _resolve_count(counts.get(4), rng, len(essays))
    order4 = _select(essays, n4, rng, shuffle_questions)
    for i, q in enumerate(order4, 1):
        out['essay'].append({'num': i, 'word': q.get('word', 'Câu'), 'stem': q['stem'], 'images': q['images']})

    return out, answer_key
