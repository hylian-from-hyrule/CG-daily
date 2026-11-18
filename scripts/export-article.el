;;; export-article.el -*- lexical-binding: t; -*-
;;; Export a single Org article to a responsive HTML page and an RSS fragment.
(require 'org)
(require 'ox-html)

(let* ((source (pop command-line-args-left))
       (destination (pop command-line-args-left))
       (stylesheet (pop command-line-args-left)))
  (unless (and source destination stylesheet)
    (error "Usage: emacs --batch -Q --script scripts/export-article.el SOURCE DEST CSS"))
  (setq source (expand-file-name source)
        destination (expand-file-name destination))
  (make-directory (file-name-directory destination) t)
  (with-current-buffer (find-file-noselect source)
    (setq-local org-html-head
                (format "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n<link rel=\"stylesheet\" href=\"%s\">"
                        stylesheet))
    (setq-local org-html-head-include-default-style nil)
    (setq-local org-html-head-include-scripts nil)
    (setq-local org-html-postamble nil)
    (setq-local org-html-preamble nil)
    (setq-local org-html-validation-link nil)
    (setq-local org-html-with-latex 'mathjax)
    (setq-local org-export-with-broken-links 'mark)
    (org-export-to-file 'html destination nil nil nil nil nil)
    (with-temp-file (concat destination ".fragment")
      (insert (org-export-as 'html nil nil t nil))))
  (message "Exported %s" destination))
