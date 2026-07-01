# CSS theme tokens

Tokenized **26 colors** and **9 font stacks** across 2 file(s); rewrote 2.

Tokens written to the `:root` of `theme-tokens.css`. Override these to re-theme.

## Semantic colors (heuristic — verify & expose in the site theme mixin)

| var | value | role |
|---|---|---|
| `--color-primary` | `#2c2e3fb2` | primary |
| `--color-secondary` | `#1b72d0da` | secondary |
| `--color-accent` | `#2437453b` | accent |
| `--color-text` | `#000000` | text |
| `--color-bg` | `#ffffff` | bg |

## Other color tokens

| var | value | uses |
|---|---|---|
| `--color-01` | `#a7b2ba80` | 19 |
| `--color-02` | `#0000001f` | 13 |
| `--color-03` | `#0000001a` | 4 |
| `--color-04` | `#a7b2ba66` | 3 |
| `--color-05` | `#00000066` | 3 |
| `--color-06` | `#00000080` | 2 |
| `--color-07` | `#1d042880` | 1 |
| `--color-08` | `#ffffff33` | 1 |
| `--color-09` | `#0000004c` | 1 |
| `--color-10` | `#00000026` | 1 |
| `--color-11` | `#dddddd` | 1 |
| `--color-12` | `#333333` | 1 |
| `--color-13` | `#00000099` | 1 |
| `--color-14` | `#6d6e7680` | 1 |
| `--color-15` | `#6c757d8e` | 1 |
| `--color-16` | `#0000003b` | 1 |
| `--color-17` | `#000000cc` | 1 |
| `--color-18` | `#00000073` | 1 |
| `--color-19` | `#34353866` | 1 |
| `--color-20` | `#000000de` | 1 |
| `--color-21` | `#a7b2ba52` | 1 |

## Next steps

1. Verify the semantic guesses; rename/remap so `--color-primary` is the real brand color.
2. Expose the semantic tokens on the **site theme mixin** (`<ns>mix:siteTheme`) so editors re-theme from the site node.
3. The Layout emits an inline `:root{}` override from those props, and links an optional uploaded override stylesheet last. See skill 03.
