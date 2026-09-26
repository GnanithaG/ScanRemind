# ScanRemind Roadmap

## Done in v2.0

- [x] Only the verified owner can delete a reminder
- [x] CSRF protection on every form
- [x] One-time codes: cryptographically random, stored hashed, 5 attempts max, 3 requests per 10 minutes per email
- [x] Cleanup of one-time codes older than 24 hours
- [x] Retry limit with exponential backoff for failed emails (INC-006)
- [x] Confirmation dialog before deleting a reminder
- [x] Timezone support: reminders stored in UTC, shown and repeated in the user's local time
- [x] Mobile layout improvements
- [x] Docker support
- [x] `flask send-due` command so delivery can run from an external cron trigger
- [x] Automated tests and CI

## Next

### Features
- [ ] Edit a reminder (time, text, repeat) from the My reminders page
- [ ] Search and filter on the My reminders page
- [ ] Unsubscribe / pause link in every reminder email
- [ ] HTML email template

### Infrastructure
- [ ] PostgreSQL option for production
- [ ] Per-IP rate limiting on `/send-otp` (currently per email address)
- [ ] Health-check endpoint for uptime monitoring
