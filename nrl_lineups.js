/* Seed file — rebuilt by cloud_fetch.py from the live Zero Tackle team lists.
   The named squad per club for the round below. The front-end uses this to
   cancel an injury-table entry for a player who is actually named in the
   side — without it, a season-long 'TBC' keeps a fit player half-out
   forever. Empty/stale is safe: namedSquad() ignores a round that doesn't
   match the round being tipped, and the model falls back to the injury
   table alone. */
window.NRL_LINEUPS = {
  "round": null,
  "teams": {
  }
};
