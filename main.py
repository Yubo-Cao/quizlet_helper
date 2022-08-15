from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from logging import Logger, StreamHandler, DEBUG
from pathlib import Path
from sys import stdout
from collections.abc import Callable
from typing import Dict, List, Tuple
from inspect import signature
from functools import partial, reduce

prog = "Quizlet Normalizer"
log = Logger(prog)
log.addHandler(StreamHandler(stdout))
log.setLevel(DEBUG)

try:
    import regex as re
except ImportError:
    log.info("Failed to import 'regex'. Fall back to 're'.")
    import re


@dataclass
class Picture:
    id: str = ""
    url: str = ""
    alt: str = ""


@dataclass
class Card:
    word: str
    definition: str
    picture: Picture = ""

    @staticmethod
    def loads(
            file: str | Path,
            word_definition_sep: str | re.Pattern,
            card_sep: str | re.Pattern,
    ) -> List["Card"]:
        with open(file, "r") as f:
            data = f.read()
        if not isinstance(word_definition_sep, re.Pattern):
            word_definition_sep = re.compile(word_definition_sep)
        if not isinstance(card_sep, re.Pattern):
            card_sep = re.compile(card_sep)
        cards = card_sep.split(data)
        return [Card(*word_definition_sep.split(wd)) for wd in cards if wd]

    @staticmethod
    def dumps(
            file: str | Path, cards: List["Card"], word_definition_sep: str, card_sep: str,
    ) -> None:
        with open(file, "w") as f:
            f.write(
                card_sep.join(
                    [
                        word_definition_sep.join([card.word, card.definition])
                        for card in cards
                    ]
                )
            )


ActionFn = Callable[[Card], Card]


class Action:
    jump_table: Dict[str, ActionFn] = {}

    def __init__(self, action: ActionFn, name: str = ""):
        if len(signature(action).parameters) != 1:
            # the above check only check if it accepts one argument or not. It does not
            # enforce type hinting.
            raise ValueError(f"Action '{name}' has invalid signature.")
        self.action = action
        self.name = name or action.__name__
        if self.name in self.jump_table:
            raise ValueError(f"Action {self.name} already exists.")
        self.jump_table[self.name] = action

    def __call__(self, card: Card) -> Card:
        return self.action(card)

    @classmethod
    def register(cls, action: ActionFn, name: str = ""):
        if isinstance(action, str):
            return partial(Action.register, name=action)
        return cls(action, name)

    @staticmethod
    def regex_substitute(
            to_be_replaced: Dict[str | re.Pattern, str], name: str
    ) -> "Action":
        try:
            to_be_replaced = {re.compile(k): v for k, v in to_be_replaced.items()}
        except re.error:
            msg = f"'regex' is required to use feature '{name}'"
            log.error(msg)
            raise ValueError(msg)

        def _impl(card: Card) -> Card:
            for k, v in to_be_replaced.items():
                card.word = k.sub(v, card.word)
                card.definition = k.sub(v, card.definition)
            return card

        return Action(_impl, name)

    @classmethod
    def apply(cls, cards: List[Card], actions: List[str]) -> List[Card]:
        for action in actions:
            if isinstance(action, str):
                action = cls.jump_table[action]
            cards = [action(card) for card in cards]
        return cards


def parse() -> Namespace:
    parser = ArgumentParser(prog)
    parser.add_argument(
        "--word-definition-seperator",
        "-w",
        default=r"\s*<sep>\s*",
        metavar="sep",
        help="Regex Separator between word and definition.",
    )
    parser.add_argument(
        "--card-seperator",
        "-c",
        default=r"\s*<card>\s*",
        help="Regex Separator between card.",
    )
    parser.add_argument(
        "--deduplicate",
        "-d",
        action="store_true",
        default=True,
        help="Deduplicate cards.",
    )
    parser.add_argument(
        "--action",
        "-a",
        nargs="+",
        default=list(Action.jump_table.values()),
        help="Action to be applied to cards.",
        choices=list(Action.jump_table.keys()),
    )
    parser.add_argument(
        "input",
        metavar="input",
        help="Input file.",
    )
    parser.add_argument(
        "output",
        metavar="output",
        help="Output file.",
    )
    return parser.parse_args()


Action.regex_substitute({r"\s+": " "}, "uniform_space")
Action.regex_substitute(
    {
        r"\s*（\s*": " (",
        r"\s*）\s*": ") ",
    },
    "uniform_parenthesis",
)
Action.regex_substitute(
    {
        r"\s*「\s*": " “",
        r"\s*」\s*": "” ",
        r"\s*『\s*": " ‘",
        r"\s*\』\s*": "’ ",
        r"(?P<chr>[『「\"“‘']){2,}\s*": r"\g<chr>",
        r"(?P<chr>[』」\"”’']){2,}\s*": r"\g<chr>",
    },
    "uniform_quotation",
)


@Action.register
def pair_quotation(card: Card) -> Card:
    match_quotation: re.Pattern = re.compile(
        r"""(?(DEFINE)
                (?P<single_start>['‘])  # match start of single-quoted quotation
                (?P<single_end>['’])    # match end of single-quoted quotation
                (?P<double_start>["“])  # match start of double-quoted quotation
                (?P<double_end>["”])    # match end of double-quoted quotation
                (?P<not>[^"“”'‘’]+)     # match anything that in between single/double-quoted content
            )
            (?P<quote>                  # match quotations
                (?&single_start)
                (?:(?&not)|             # match not or another recursive quote 1 or more times
                    (?&quote)
                )++(?&single_end)|      # match closing single quotation mark
                (?&double_start)        # same as above
                (?:(?&not)|
                    (?&quote)
                )++(?&double_end)
            )""",
        re.X,
    )

    def _impl(s: str) -> str:
        char_arr: List[str] = list(s)
        for match in match_quotation.finditer(s):
            # iterate over nested quotation
            level = List[Tuple[int, int]]
            levels: List[level] = []
            for span in match.spans("quote"):
                # iterate over nest
                if not levels:
                    levels.append([span])
                    continue
                lo, hi = (
                    min(levels[0], key=lambda t: t[0])[0],
                    max(levels[0], key=lambda t: t[1])[1],
                )
                span_lo, span_hi = span
                if span_lo < lo and hi < span_hi:  # contains
                    levels.insert(0, [span])
                else:
                    levels[0].insert(0, span)
            dbl = True
            for level in levels:
                for quote in level:
                    lo, hi = quote
                    char_arr[lo] = "“" if dbl else "‘"
                    char_arr[hi - 1] = "”" if dbl else "’"
                    print(quote)
                dbl = not dbl
        return "".join(char_arr)

    card.word = _impl(card.word)
    card.definition = _impl(card.definition)
    return card


def sentence_tokenize(s: str) -> List[str]:
    """
    Tokenize a sentence into words. Notice this would
    not work if sentences does not contain a space between end of sentence and next sentence.
    :param s: sentence to be tokenized.
    :return: list of sentences.
    """
    return re.split(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s", s)


@Action.register
def pair_exclamation(card: Card):
    def _impl(s: str) -> str:
        sentences = sentence_tokenize(s)
        for i, sentence in enumerate(sentences):
            if sentence.endswith("!") and not sentence.startswith("¡"):
                sentences[i] = "¡" + sentence
            if not sentence.startswith("¡") and sentence.endswith("!"):
                sentences[i] = sentence + "!"
            if sentence.startswith("¿") and not sentence.endswith("?"):
                sentences[i] = sentence + "?"
            if not sentence.startswith("¿") and sentence.endswith("?"):
                sentences[i] = "¿" + sentence
        return " ".join(sentences)

    card.word = _impl(card.word)
    card.definition = _impl(card.definition)
    return card


@Action.register
def trim_space(card: Card):
    card.word = card.word.strip()
    card.definition = card.definition.strip()
    return card


def deduplicate(cards: List[Card]) -> List[Card]:
    """
    Remove duplicate words.
    :param cards: list of cards.
    :return: list of cards without duplicates.
    """
    seen: Dict[str, Card] = {}
    for card in cards:
        prefixes = ["el", "la", "los", "las", "un", "una", "unos", "unas"]
        root = reduce(lambda r, p: r.removeprefix(p), [card.word] + prefixes)
        if root not in seen:
            seen[root] = card
            continue
        log.warning(f"Duplicate word: {card.word}")
        other = seen[root]
        if other.definition != card.definition:
            log.warning(
                f"Different definition: {seen[root].definition} vs {card.definition}"
            )
        word = max(card.word, other.word, key=len)
        definition = max(card.definition, other.definition, key=len)
        seen[root] = Card(word, definition, card.picture)  # TODO: GUI and let user pick
        continue
    return list(seen.values())


def main():
    args = parse()
    cards = Card.loads(args.input, args.word_definition_seperator, args.card_seperator)
    cards = Action.apply(cards, args.action)
    if args.deduplicate:
        cards = deduplicate(cards)
    Card.dumps(args.output, cards, "\t", "\n")


if __name__ == "__main__":
    main()
