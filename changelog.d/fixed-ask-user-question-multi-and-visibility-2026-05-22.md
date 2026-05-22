**AskUserQuestion** in the conversation reader now renders **all** questions
(the tool can carry up to 4 in one call — earlier we silently dropped
everything past `questions[0]`). Each question is its own accent-bordered
callout with header, question text, and bulleted options + descriptions.
The block is also kept visible when "hide tools" is toggled on, since it
is a prompt directed at the user rather than a side-effect tool call.
