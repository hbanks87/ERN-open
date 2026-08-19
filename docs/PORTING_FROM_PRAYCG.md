# Porting from PRAYCG

MCS-ERN-Flanker borrows the following engineering ideas from PRAYCG:

- explicit run configuration
- file inventory
- QC gates
- decision logs
- sensitivity branches
- offline plain-English reports

It does **not** borrow PRAYCG meaning modules:

```text
MRED, A-MRED, DGA, NUPI, TTI, NIP, CET/EET, Topo-OSM
```

Those are intentionally absent because a Flanker/ERN/anxiety dataset asks a different question.
