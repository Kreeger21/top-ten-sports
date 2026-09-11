# NBA possession evidence report

- Games: 3,697
- Possessions: 773,875
- Players covered: 770
- Complete reconstructed lineup coverage: 71.9%
- Maximum frozen-formula Overall: 84
- 80+/85+/90+: 13/0/0

## Ty Jerome

{
  "player_id": "4065733",
  "player_name": "Ty Jerome",
  "position": "SG",
  "overall": 82,
  "raw_score": 76.69,
  "shot_creation": 90.55,
  "ball_handling": 67.3,
  "transition": 82.0,
  "post_offense": 62.0,
  "creation_burden": 36.236,
  "role_context": "Primary Creator",
  "unassisted_make_rate": 0.54939,
  "possessions": 2825.95,
  "evidence_quality": 69,
  "formula_coverage": 100,
  "rank": 8
}

## Transition validation

{
  "Half Court": {
    "count": 69104,
    "share": 0.0893
  },
  "High Confidence Transition": {
    "count": 27853,
    "share": 0.036
  },
  "Likely Transition": {
    "count": 244963,
    "share": 0.3165
  },
  "Unknown": {
    "count": 431955,
    "share": 0.5582
  }
}

## Low-role inflation flags

1 diagnostic flags; these are not rating penalties.

## Compression conclusion

Possession evidence reduced several role-inflation cases, but the maximum raw positional value remains below 79 and evidence quality remains limited by unavailable optical defense, screening, off-ball movement, and complete passing data. The frozen logistic display curve also maps that narrow raw range to a maximum of 84. A dedicated Overall display-curve calibration phase is now justified, but it should remain separate from evidence construction and retain these missing-evidence warnings.