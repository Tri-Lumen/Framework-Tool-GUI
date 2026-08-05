# Wiki sources

These pages are the source for the project's
[GitHub wiki](https://github.com/Tri-Lumen/Framework-Tool-GUI/wiki). They
live in the repository so they are reviewed in pull requests alongside the
code they describe, rather than drifting in a wiki nobody diffs.

## Publishing

The GitHub wiki is its own git repository. To push these to it:

```bash
git clone https://github.com/Tri-Lumen/Framework-Tool-GUI.wiki.git
cp wiki/*.md Framework-Tool-GUI.wiki/
cd Framework-Tool-GUI.wiki && git add -A && git commit -m "Sync wiki from repo" && git push
```

(The wiki has to be initialised once through the GitHub web UI before that
clone works — create any page and save it.)

## Page names

GitHub derives a wiki page's title from its filename, and double-bracket
wiki links resolve against those titles with spaces mapped to hyphens. `_Sidebar.md` is
special-cased by GitHub and renders on every page.

## Image links

The pages reference `../docs/screenshots/*.png`, which resolves inside this
repository but **not** on the wiki, where there is no parent directory. When
publishing, either copy `docs/screenshots/` into the wiki repo as well or
rewrite the links to absolute
`https://raw.githubusercontent.com/Tri-Lumen/Framework-Tool-GUI/main/docs/screenshots/...`
URLs.
