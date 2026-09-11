# NBA evidence source matrix

| Skill | Local evidence | hoopR | pbpstats | NBA Stats | Synergy | Selected strategy |
|---|---|---|---|---|---|---|
| Shot creation | Unassisted makes, volume, zones | Derived | Possession context | Tracking blocked | Direct play types; authenticated | Derived self-created evidence |
| Ball handling | TOV, AST/TOV, self-creation | Proxy | Possession context | Direct tracking blocked | Direct play types; authenticated | Explicit proxy confidence |
| Passing | AST and AST/TOV | Direct/derived | Possession context | Passes blocked | Root-player context; authenticated | Preserve narrow playmaking |
| Transition | No reliable flag | Text insufficient | Derivable possession context | Blocked | Direct tagged possessions | Leave fallback |
| Post offense | Hook action and sample | Narrow derived | Possession context | Blocked | Direct PostUp | Evidence-gated hook estimate |
| Off-ball | Assisted makes | Narrow derived | Possession context | Catch-and-shoot blocked | SpotUp/Cut/OffScreen | Low-confidence proxy |
| Perimeter defense | STL/fouls | Narrow direct | Team impact only | Matchups blocked | Defender tags | Low-confidence fallback |
| Interior defense | BLK/DREB/fouls | Narrow direct | Team impact only | Rim matchup blocked | Defender/post tags | Conservative proxy |
| Screening | None | Unavailable | Incomplete | Screen assists blocked | P&R player tags | Leave fallback |

`pbpstats` adds possessions, lineups, possession start/end context, and shot-zone splits, but does not itself supply optical tracking or Synergy play-type labels.
