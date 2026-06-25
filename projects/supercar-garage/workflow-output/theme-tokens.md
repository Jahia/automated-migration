# CSS theme tokens

Tokenized **84 colors** and **18 font stacks** across 6 file(s); rewrote 5.

Tokens written to the `:root` of `theme-tokens.css`. Override these to re-theme.

## Semantic colors (heuristic — verify & expose in the site theme mixin)

| var | value | role |
|---|---|---|
| `--color-primary` | `#c08a55f2` | primary |
| `--color-secondary` | `#c08a55a6` | secondary |
| `--color-accent` | `#ff0000b2` | accent |
| `--color-text` | `#000000` | text |
| `--color-bg` | `#ffffff` | bg |

## Other color tokens

| var | value | uses |
|---|---|---|
| `--color-01` | `#ffffff1a` | 20 |
| `--color-02` | `#ffffff66` | 19 |
| `--color-03` | `#ffffff80` | 18 |
| `--color-04` | `#0000001a` | 18 |
| `--color-05` | `#ffffffe6` | 12 |
| `--color-06` | `#00000033` | 12 |
| `--color-07` | `#a7b2ba80` | 12 |
| `--color-08` | `#eeeeee` | 10 |
| `--color-09` | `#00000080` | 10 |
| `--color-10` | `#333333` | 9 |
| `--color-11` | `#ffffff4c` | 8 |
| `--color-12` | `#000000bf` | 8 |
| `--color-13` | `#000000d9` | 8 |
| `--color-14` | `#000000e6` | 8 |
| `--color-15` | `#ffffff33` | 7 |
| `--color-16` | `#14141480` | 6 |
| `--color-17` | `#ffffffbf` | 5 |
| `--color-18` | `#00000026` | 5 |
| `--color-19` | `#00000066` | 5 |
| `--color-20` | `#ffffffd9` | 5 |
| `--color-21` | `#0000001f` | 5 |
| `--color-22` | `#00000059` | 4 |
| `--color-23` | `#323232b2` | 4 |
| `--color-24` | `#0000000d` | 4 |
| `--color-25` | `#dddddd` | 4 |
| `--color-26` | `#f6f6f61a` | 4 |
| `--color-27` | `#ffffff05` | 4 |
| `--color-28` | `#f6f6f6c7` | 4 |
| `--color-29` | `#00000099` | 3 |
| `--color-30` | `#999999` | 2 |
| `--color-31` | `#111111` | 2 |
| `--color-32` | `#323232cc` | 2 |
| `--color-33` | `#ffffffcc` | 2 |
| `--color-34` | `#21f8f8` | 2 |
| `--color-35` | `#cccccc` | 2 |
| `--color-36` | `#0000004c` | 2 |
| `--color-37` | `#666666` | 2 |
| `--color-38` | `#555555` | 2 |
| `--color-39` | `#30303033` | 2 |
| `--color-40` | `#18042233` | 2 |
| `--color-41` | `#ffffff1c` | 2 |
| `--color-42` | `#f6f6f6b8` | 2 |
| `--color-43` | `#f6f6f624` | 2 |
| `--color-44` | `#0000008c` | 2 |
| `--color-45` | `#c08a552e` | 2 |
| `--color-46` | `#8f5d342e` | 2 |
| `--color-47` | `#ffffff0a` | 2 |
| `--color-48` | `#ffffff0d` | 2 |
| `--color-49` | `#ffffff09` | 2 |
| `--color-50` | `#f6f6f6eb` | 2 |
| `--color-51` | `#ffffff0e` | 2 |
| `--color-52` | `#8f5d3438` | 2 |
| `--color-53` | `#c08a5524` | 2 |
| `--color-54` | `#c08a5559` | 2 |
| `--color-55` | `#c08a5547` | 2 |
| `--color-56` | `#ffffff08` | 2 |
| `--color-57` | `#ffffff03` | 2 |
| `--color-58` | `#c08a5552` | 2 |
| `--color-59` | `#c08a550d` | 2 |
| `--color-60` | `#00000040` | 1 |
| `--color-61` | `#ff0000` | 1 |
| `--color-62` | `#ffffff26` | 1 |
| `--color-63` | `#777777` | 1 |
| `--color-64` | `#ffffff99` | 1 |
| `--color-65` | `#080807bf` | 1 |
| `--color-66` | `#11151abf` | 1 |
| `--color-67` | `#6d6e7680` | 1 |
| `--color-68` | `#6c757d8e` | 1 |
| `--color-69` | `#18042240` | 1 |
| `--color-70` | `#18042280` | 1 |
| `--color-71` | `#ffffff73` | 1 |
| `--color-72` | `#1d04281a` | 1 |
| `--color-73` | `#3008434c` | 1 |
| `--color-74` | `#34353866` | 1 |
| `--color-75` | `#2c2e3fb2` | 1 |
| `--color-76` | `#000000de` | 1 |
| `--color-77` | `#b68b3b8f` | 1 |
| `--color-78` | `#b68b3b4c` | 1 |
| `--color-79` | `#ffffff8f` | 1 |

## Next steps

1. Verify the semantic guesses; rename/remap so `--color-primary` is the real brand color.
2. Expose the semantic tokens on the **site theme mixin** (`<ns>mix:siteTheme`) so editors re-theme from the site node.
3. The Layout emits an inline `:root{}` override from those props, and links an optional uploaded override stylesheet last. See skill 03.
