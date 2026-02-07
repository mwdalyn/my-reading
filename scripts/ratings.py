'''Triggered upon completion or a book; or, alternatively, triggered on workflow dispatch.
For books that are closed or status == "completed" and rating is missing, parse their comments and look for a comment
with the substring "rating:{}" and parse rating (out of 10) from {}.'''