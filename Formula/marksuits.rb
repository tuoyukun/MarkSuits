# Homebrew formula for Mark: the `mark` CLI and, on macOS, Mark.app (menu bar; runs the board).
# This repo is its own tap:
#   brew tap tuoyukun/marksuits https://github.com/tuoyukun/MarkSuits
#   brew trust tuoyukun/marksuits
#   brew install marksuits && open "$(brew --prefix)/opt/marksuits/Mark.app"
# The Claude Code plugin is installed separately (`claude plugin install mark@marksuits`).
class Marksuits < Formula
  desc "Multi-agent development workflow for Claude Code: mark CLI and web board"
  homepage "https://github.com/tuoyukun/MarkSuits"
  url "https://github.com/tuoyukun/MarkSuits.git", tag: "mark--v0.59.0"
  license "MIT"
  head "https://github.com/tuoyukun/MarkSuits.git", branch: "main"

  depends_on "python@3.13"

  conflicts_with "mark", because: "both install a `mark` executable"

  def install
    libexec.install Dir["plugins/mark/*"], "plugins/mark/.claude-plugin"
    (bin/"mark").write <<~SH
      #!/bin/bash
      exec "#{formula_opt_bin("python@3.13")}/python3.13" "#{libexec}/bin/mark" "$@"
    SH
    build_app if OS.mac?
  end

  def build_app
    contents = prefix/"Mark.app/Contents"
    (contents/"MacOS").mkpath
    system "swiftc", "-O", "-module-cache-path", buildpath/"swift-cache",
           "-o", contents/"MacOS/Mark", "macos/Mark.swift"
    (contents/"Info.plist").write <<~XML
      <?xml version="1.0" encoding="UTF-8"?>
      <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
      <plist version="1.0"><dict>
        <key>CFBundleIdentifier</key><string>com.marksuits.mark</string>
        <key>CFBundleName</key><string>Mark</string>
        <key>CFBundleExecutable</key><string>Mark</string>
        <key>CFBundlePackageType</key><string>APPL</string>
        <key>CFBundleShortVersionString</key><string>#{version}</string>
        <key>LSUIElement</key><true/>
        <key>LSMinimumSystemVersion</key><string>13.0</string>
        <key>MarkCLI</key><string>#{opt_bin}/mark</string>
        <key>MarkApp</key><string>#{opt_prefix}/Mark.app/Contents/MacOS/Mark</string>
      </dict></plist>
    XML
  end

  def caveats
    <<~EOS
      Board sessions run Claude Code with the Mark plugin; install it once:
        claude plugin marketplace add tuoyukun/MarkSuits --scope user
        claude plugin install mark@marksuits --scope user
      Start the menu bar app (it runs the board; Preferences has "Launch Mark at login"):
        open "#{opt_prefix}/Mark.app"
      Its Open item, or `mark board`, opens the board signed in (decisions need that).
    EOS
  end

  test do
    assert_match(/^\d+\.\d+\.\d+$/, shell_output("#{bin}/mark --version").strip)
  end
end
