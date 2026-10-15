# Upload this source snapshot

GitHub authentication for `samskiezz` is working, but the connected integration rejected repository creation with HTTP 403 (`Resource not accessible by integration`). No GitHub upload has succeeded. The latest user instruction authorises uploading this unfinished platform.

Create an **empty private** repository named `sherlock-osint`, without a generated README, and enable it for the connected GitHub integration. The prepared repository is `/workspace/sherlock-osint-github`; no other project needs to be overwritten.

Once access is available, run in that directory:

```bash
git remote add origin https://github.com/samskiezz/sherlock-osint.git
git push -u origin main
```

If using the ZIP on another machine, initialise a repository and commit its source first. If using the Git bundle, clone it with `git clone sherlock-osint-source.bundle sherlock-osint`, then use the GitHub remote above. Authentication must be available on that machine; never embed a token in the remote URL.

The source excludes the original workspace history, credentials, case databases, acquired evidence files and installed model weights. The existing app and evidence vault remain in the original running workspace. `IMPLEMENTATION_GAPS.json` records unfinished platform requirements.
