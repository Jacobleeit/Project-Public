# Upload this project to GitHub

## Upload from your Windows computer

1. Download `backup-report-automation.zip` and right-click it > **Extract All**.
2. Open the extracted `backup-report-automation` folder. You should see `README.md`, `backup_report.py`, the sample CSVs, and the other project files.
3. Sign in to your GitHub account and open https://github.com/Jacobleeit/Project-Public.
4. Select **Add file > Upload files**. If the repository is completely empty, select **uploading an existing file** on its setup page.
5. Select all the project files inside the extracted folder and drag them onto the upload area. Upload the extracted files, not just the ZIP. Keep `README.md` at the repository root so GitHub displays the instructions.
6. Check the displayed filenames. If your repository already has files with the same names, compare them before replacing anything.
7. Use the commit message `Add initial backup report automation tool`. For your new repository, commit directly to its default branch if offered, then click **Commit changes**. If GitHub requires a pull request, follow that flow and merge it after review.
8. Return to the repository page and confirm the code and README are visible. Open the page while signed out to confirm public visibility before using it in an open-source application.

Direct upload shortcut if your default branch is `main`:
https://github.com/Jacobleeit/Project-Public/upload/main

If the shortcut does not work, use the repository page and its upload button; your branch may have a different name.

Official GitHub upload instructions:
https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository

## Try it before submitting an application

Open `example_report.html` for a preview, then run `RUN_DEMO.cmd` on Windows with Python 3.10+ installed. The demo should report 8 objects: 3 OK, 2 warning, and 3 critical. See README for using your own normalized CSVs.

## Accurate application description after upload

The following is under 500 characters and describes this initial release:

> I maintain an early-stage open-source backup-reporting tool for IT work automation. It reads CSV exports, flags failed or overdue backups and missing objects, and produces HTML, CSV, and JSON summaries. The repository includes fictional sample data, documentation, automated tests, and an MIT license. I plan to use Codex to improve reliability and add export adapters so other administrators can reuse it.

Use this wording only after publishing the files and reviewing the project. Report adoption honestly; no stars, downloads, or production deployments have been established. Publishing a working tool does not guarantee acceptance into the support program.
