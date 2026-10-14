# Email: support@runonflux.io

Helpdesk receives email into tickets and sends replies from the same address.

## Set up

1. In Google Workspace, make sure `support@runonflux.io` is a mailbox Helpdesk can log in to. A Google Group cannot be polled; if `support@` is a group today, add a mailbox user to it or turn it into a user.
2. In Helpdesk, open **Settings → Email Accounts → New**, choose **Gmail**, and connect with OAuth (preferred) or an app password.
3. Turn on **incoming** and **outgoing**, and make it the default outgoing account.
4. Send a test email to `support@` and check that it becomes a ticket. Reply from Helpdesk and check that it arrives.
5. When the site is ready to send for real, set `MUTE_EMAILS=0` in `deploy/.env` and restart `migrate`. With `MUTE_EMAILS=1` nothing leaves the server, which is what you want during the import.

SPF and DKIM do not change, because mail still goes through Google.

## Cutover from Freshdesk

1. Import history with emails muted ([freshdesk-import.md](freshdesk-import.md)).
2. Stop Freshdesk from fetching `support@`: remove its custom mailbox, or stop the forwarding to Freshdesk.
3. Connect the mailbox in Helpdesk (above) and unmute email.
4. Run the importer once more to pick up tickets that changed during the switch. It skips everything it already has.
5. Move the `support.runonflux.io` DNS record.

## Templates

The acknowledgement, reply and feedback emails live in **HD Settings**. Keep them short and point to `https://support.runonflux.io/support`.
