# udg-media

Public media for **Uncommon Discounts Galore** (https://claude.ai/artifact/M9WnhVjLs42ruk2pRWbHA4).

- `videos/` holds the daily faceless deal videos (9:16, 1080x1920, about 30 seconds). Each file is imported into vidIQ by its raw GitHub address and posted to TikTok, YouTube Shorts and the Facebook Page after the owner approves the post.
- `videokit/` makes those videos: `make_video.py` turns a short spec (on-screen text and voiceover lines for the day's top deal) into an MP4, using `scenes.html` for the frames and the Kokoro voice model (Apache-2.0) for narration.

Photos in `videokit/img/` are from Unsplash (Marek Studzinski, Zoshua Colah, Jake Nackos, Jed Owen), used under the Unsplash License.

Coupon codes are paid member content and never appear in this repository or in any video.
