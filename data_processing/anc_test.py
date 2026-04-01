#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import spacy

TEST_SENTENCES = [
    "Mary gave a book to me.",
    "Mary gave me a book.",
    "I gave up the book.",
    "I gave the book up.",
    "I look for my book."
]


def print_sentence(sent):
    print("=" * 100)
    print("SENT:", sent.text)
    print()

    print("TOKENS:")
    for tok in sent:
        print(
            f"i={tok.i:<3} "
            f"text={tok.text:<15} "
            f"lemma={tok.lemma_:<15} "
            f"pos={tok.pos_:<8} "
            f"tag={tok.tag_:<8} "
            f"dep={tok.dep_:<10} "
            f"head={tok.head.text}"
        )
    print()

    print("DEPENDENCY TREE (child view):")
    for tok in sent:
        children = list(tok.children)
        if children:
            child_str = ", ".join(f"{c.text}/{c.dep_}" for c in children)
            print(f"{tok.text} -> {child_str}")
    print()


def main():
    nlp = spacy.load("en_core_web_md")

    for i, text in enumerate(TEST_SENTENCES, start=1):
        print(f"\n########## EXAMPLE {i} ##########\n")
        doc = nlp(text)
        for sent in doc.sents:
            print_sentence(sent)


if __name__ == "__main__":
    main()