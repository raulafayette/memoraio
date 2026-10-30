# Manual controls, folders and Instagram

Downloads is the initial page. A single video URL requests one file; a channel, profile or playlist URL builds a batch. Output choices are MP3 and MP4. Acquisition has no recurring schedule.

Each transcription card has compact Start/Pause/Resume, Update, Open folder and View TXT controls. Update inventories metadata without requesting media or transcription. Counters show verified available TXT, distinct identified items and remaining items. A partial inventory is labeled partial. Channels are separated into downloading now, queued/preparing, and idle/paused/finished groups. Four labeled bars distinguish discovery (blue), the user-started batch (amber), the individual TXT (light blue), and all completed channel content (violet). Unknown discovery/current fractions stay indeterminate. Measured percentages during individual processing are labeled as stage progress; 100% completed is reserved for verified TXT availability. Each newly completed item receives a short 100% receipt followed by a zero reset before the next item. A burst of completions is acknowledged sequentially. Old files are not replayed as new completions when opening the page. The general transcription page also shows consolidated progress, counting each identified item only once even when shared by multiple channels.

Cards show measured content bytes and explicitly approximate pending text space/time. Shared models and the catalog are excluded from per-channel content bytes. Missing durations use a stated ten-minute assumption. Once enough jobs finish, time ranges use observed processing times. These ranges cannot predict provider delays or content without captions.

Settings selects the default TXT folder through the native macOS folder picker. New channels create a subfolder there immediately. Each channel can override the destination. Changing destinations queues local standalone TXT copies and preserves old copies and user-edited text. The displayed directory opens Finder. The canonical checked transcript remains in the managed library.

Home summaries count verified, available transcripts and MP3/MP4 files, including this calendar week and month in the viewer's timezone. Reprocessing and additional folder copies do not create additional transcript counts. Historical media with no reliable completion date contributes to the total, not an invented period count.

YouTube transcription remains caption-only. Public Instagram feed/reels can work without login when Instagram permits access. Stories, highlights and private content require a local account session with suitable access. Only protected scope choices show the connection panel. The optional native login window uses the official Instagram website; the user signs in directly. Session cookies are stored locally with restricted permissions and are never returned by the status API. Disconnect removes this app's saved session.

Instagram speech transcription requires the explicitly enabled local ASR option and a configured pinned model. It requests separate audio where available, otherwise extracts audio from temporary media. Temporary audio/checkpoints are removed after validated publication. Instagram descriptions are metadata, not speech transcripts. The service can refuse, rate-limit or change access; successful public testing does not establish authenticated stories/highlights support for every account.

## Three channels in parallel

The local service runs three acquisition workers and three dedicated transcription workers. A separate local worker publishes TXT exports and performs other library work. Start each desired channel manually. There is no scheduled start of additional channels.

Each acquisition/transcription lane atomically reserves at most one job per channel. Persisted channel turns give the next free slot to a waiting channel before repeatedly selecting a large channel. Files shared by channels retain the existing unique active job and item locks. Global and individual pause, leases, cooldowns and checksum validation still apply. The supervisor monitors every worker slot and restores failed workers. Three slots provide capacity, not a guarantee that a platform always permits three successful transfers.

## Paused queue for newly added channels

Adding a channel creates its TXT folder and a persistent paused-queue entry without requesting discovery or transcription. The paused queue is shown separately from active transfers, released/waiting channels and finished/inactive channels. Its order survives restarting the app. Updating counts alone does not release the channel.

Choose the content type and click Release to start a new channel. An existing paused batch resumes with the same saved scope and checkpoints. Pausing a running channel returns it to the paused queue; releasing it leaves other paused channels untouched. Re-adding an already active source preserves its existing batch. The three parallel slots are shared only by released work.

## Recurring channel workspace

Channel cards show verified TXT availability, pending jobs, remaining items, the last completed consultation and newly identified items compared with the previous catalog. Discovery snapshots persist in SQLite. First inventories are labeled as initial; partial scans are not presented as proof that a channel has no further content. Newly identified means new to this catalog comparison, not necessarily newly published. The New tab lists the observed titles.

Platform filters and distinct YouTube/Instagram groups, channel search, state filters and checkboxes organize recurring work. Start selected and Start all explicitly release work into the three supervised slots. Active work is not paused by a collective start. Invalid/unavailable requests are reported per channel without discarding other valid requests. New registrations remain paused until an explicit start.

Per-channel image buttons retain accessible names and hover titles. Pending controls acknowledge immediately; a lightweight endpoint confirms that pause/cancel has reached running jobs. A late inventory snapshot cannot replace a more recent control acknowledgement. Quick pause/resume is transactional and does not strand a job that was still acknowledging pause. Global pause remains explicit.

## Completion-month directories

Readable TXT copies are organized as `channel/transcricoes/YYYY-MM/title.txt`, using the transcript completion timestamp in the configured archive timezone. Music/video shortcuts use `channel/musicas/YYYY-MM/` and `channel/videos/YYYY-MM/` with the recorded media completion date. Undated legacy media uses `sem-data` rather than an invented timestamp. Content-addressed original objects and transcript versions remain in their managed locations.

A later copy/export retains the original completion month. Reorganization preserves edited files, verifies managed copies and removes only identical managed flat copies after their monthly copy is durable. Repeated export of the same valid TXT does not rewrite it. Directory choices still apply to the channel base; monthly folders are created inside it.

## Download manager

The media page has a link entry, MP4/MP3 selector, queue and completed-file tabs. A channel/profile/playlist URL still expands into a batch automatically. Active rows expose real counts, an indeterminate discovery indicator until a total exists, pause/resume and stop. Completed rows list checksum-verified files with Save MP3/MP4 actions. Instagram connection is requested only for protected scopes. The media page loads its own queue without waiting for the transcription catalog.
