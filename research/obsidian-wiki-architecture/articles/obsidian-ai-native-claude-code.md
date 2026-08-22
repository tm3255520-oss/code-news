Source: https://medium.com/@martk/turning-obsidian-into-an-ai-native-knowledge-system-with-claude-code-27cb224404cf
Fetched: 2026-08-01T10:37:43

Title: Turning Obsidian into an AI-Native Knowledge System with Claude Code

URL Source: http://medium.com/@martk/turning-obsidian-into-an-ai-native-knowledge-system-with-claude-code-27cb224404cf

Published Time: 2026-03-09T08:36:00Z

Markdown Content:
[![Image 1: Mart Kempenaar](https://miro.medium.com/v2/resize:fill:32:32/1*mnm_UsUP3MqdvskIGVrBAg.jpeg)](https://medium.com/@martk?source=post_page---byline--27cb224404cf---------------------------------------)

5 min read

Mar 9, 2026

I have been using Obsidian for a few years. In that time I have tried a fair amount of AI tools attempt to make personal knowledge management smarter: AI-powered semantic search, chat interfaces layered on top of vaults, plugins that summarize notes or suggest links. Some of them were useful. None of them really changed how I work.

That was until I tried Claude Code, which has fundamentally changed the way I interact with my Obsidian Vaults. It now actually feels like I have a very capable, personal assistant embedded in my vault that exactly behaves the way I want it to. In this guide, I will cover how to set up Claude Code in your Obsidian Vault and what some of its powerful capabilities are.

## Prerequisites

Before getting started, there are a few things that you need:

*   **Claude Pro plan or higher.** Claude Code is only available on paid Claude plans, so a Pro subscription or above is required.
*   **Basic comfort with the terminal.** You should know how to open Claude Code in your Obsidian Vault.

There is some initial configuration involved, and getting everything to behave exactly the way you want takes some iteration. What makes this setup stand out though is the combination of contextualized skills and Claude instructions that live directly inside your vault. That is what turns Claude from a general-purpose assistant into something that understands your specific system and follows your personal conventions, and makes it feel like an actual personalized personal assistant.

## Setting up the system

**CLAUDE.md**

The brain of the whole setup is the CLAUDE.md file. This is a plain markdown file that lives inside your vault and instructs Claude Code exactly how to behave as an assistant to your vault. It defines the folder structure of your vault, the conventions you follow, which skills to invoke and when, and any other preferences that shape how Claude operates. Without it, Claude has no awareness of your personal system. With it, every interaction is grounded in how your vault actually works and how you want Claude to specifically behave.

**Claude Skills**

A set of Claude Code skills handle the specific capabilities you need inside a vault. Skills are Claude Code’s way of giving the model persistent, reusable instructions for a specific domain, which in this case are ways of interacting with our Obsidian Vault.

The **obsidian-cli** skill is what gives Claude the ability to directly interact with your vault. It works in combination with the Obsidian CLI, a tool created by Obsidian that exposes your vault to external programs (which you have to turn on in the settings first). The skill teaches Claude how to use the CLI correctly, covering reading notes, creating and updating files, searching content, managing tasks, and more.

## Get Mart Kempenaar’s stories in your inbox

Join Medium for free to get updates from this writer.

Remember me for faster sign in

The **obsidian-markdown** and **obsidian-base**s skills add to this by ensuring that whatever Claude creates follows the right format. The obsidian-markdown skill handles correct Obsidian syntax, including wikilinks, callouts, frontmatter properties, and embeds. The obsidian-bases skill covers working with Obsidian Bases. Together they make sure that the output Claude produces fits naturally into your vault rather than requiring manual cleanup.

All of these skills are available in a public GitHub repository created by the founder of Obsidian, and can be found here: [https://github.com/kepano/obsidian-skills](https://github.com/kepano/obsidian-skills)

## Getting started

Getting the Obsidian skills into your setup is a matter of cloning the repository and copying over the skills inside of the `skills` folder to `yourvaultname/.claude/skills`

Once the skills are in place, open Claude Code inside your vault folder. The most important step from there is creating your CLAUDE.md file. The best way to do this is to instruct Claude to go through your existing vault structure first. Ask it to explore each folder, understand what it contains and how you use it, and then generate the CLAUDE.md based on that analysis. The result should be a clear overview of how your vault is structured, what each folder means, and the conventions Claude should follow when working inside it. Then, also instruct Claude to include common ways you interact with the system and any specific writing styles that you want it to adhere to.

This setup on its own is already quite powerful: it enables Claude to find its way through your vault and perform all kinds of actions per your request.

## Making it yours with custom skills

Beyond the core skills, you can create custom skills directly inside your vault folder for specific workflows you use regularly. You simply describe to Claude what you want the skill to do and ask it to create one, and it will generate the skill definition in your local folder automatically. From that point on, Claude can invoke it whenever that workflow comes up.

### Weekly Reflection Skill

A good example of what custom skills make possible is my weekly reflection workflow. I have set up this skill in a way that Claude will ask me a default set of questions that are inside my Templates/Weekly reflection note. It will ask each question in a conversational manner and ask follow ups based on my answers if it sees fit. Then it will also go through the notes that I created in the past week. It will combine the answers that I gave to the weekly reflection questions and a recap of the notes that I created in a new weekly reflection note.

Finally, Claude will use another skill called `inbox-cleanup` to categorize all notes created in the past week and decide what to do with them: either move notes to a permanent place in my vault based on content importance (it knows which files are stored where if you created the CLAUDE.md correctly) or it will archive it. Per action group, it will ask me for permission and then actually perform the moving/archiving action on the note(s).

## Where this leaves you

What this setup ultimately gives you is a personal knowledge base that Claude can work inside of. Your notes, your structure, your conventions, all of it becomes context that Claude carries into every interaction. The more you refine it through your CLAUDE.md and your own custom skills, the more it reflects the way you actually think and work.

It took me some time to get it running the way I wanted, but it has genuinely shifted how I use Obsidian day to day. If you give this a try, I hope it does the same for you.

Press enter or click to view image in full size

![Image 2](https://miro.medium.com/v2/resize:fit:700/1*5DylfRbrStBXsrr7Jdf2qQ.jpeg)

