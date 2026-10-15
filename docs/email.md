# Email: support@runonflux.io

Helpdesk receives email into tickets and sends replies from the same address.

## Set up

1. In Google Workspace, make sure `support@runonflux.io` is a mailbox Helpdesk can log in to. A Google Group cannot be polled; if `support@` is a group today, add a mailbox user to it or turn it into a user.
2. In Helpdesk, open **Settings → Email Accounts → New**, choose **Gmail**, and connect with OAuth (preferred) or an app password.
3. Turn on **incoming** and **outgoing**, and make it the default outgoing account.
4. Send a test email to `support@` and check that it becomes a ticket. Reply from Helpdesk and check that it arrives.
5. When the site is ready to send for real, set `MUTE_EMAILS=0` in `deploy/.env` and run `docker compose … up -d` (the `migrate` service applies it on every start, so `.env` is the one place to change it). With `MUTE_EMAILS=1` nothing leaves the server, which is what you want during the import.

When a mailbox is first connected, Helpdesk pulls in its recent mail and makes tickets of it. Set **Email Sync Option** to *UNSEEN* on the email account, and mark everything already in `support@` as read beforehand, or the tickets you imported from Freshdesk come in a second time as new ones.

SPF and DKIM do not change, because mail still goes through Google.

## Cutover from Freshdesk

1. Import history with emails muted ([freshdesk-import.md](freshdesk-import.md)). This can happen days ahead.
2. Stop Freshdesk from fetching `support@`: remove its custom mailbox, or stop the forwarding to Freshdesk. From here on new mail waits in the mailbox.
3. Run the importer with `since` set to the day of the full import. It brings over the tickets and replies that arrived in Freshdesk since then. Email must still be muted.
4. Mark everything in `support@` that Freshdesk already handled as read, then connect the mailbox in Helpdesk (above). Mail that arrived after step 2 becomes new tickets.
5. Unmute email (`MUTE_EMAILS=0`, `up -d`) and move the `support.runonflux.io` DNS record.

## Templates

The acknowledgement, reply and feedback emails live in **HD Settings**. Keep them short and point to `https://support.runonflux.io/support`.
