Source: https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/
Fetched: 2026-08-01T10:36:41

Title: Quickly Organize Notes in Obsidian

URL Source: http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/

Published Time: 2022-08-30T15:17:58+00:00

Markdown Content:
[Skip to content](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#primary)

[Obsidian Rocks](https://obsidian.rocks/)

Exploring knowledge management with Obsidian.

*   [![Image 7: 🫣](https://s.w.org/images/core/emoji/17.0.2/svg/1fae3.svg) Privacy](https://obsidian.rocks/privacy-policy/)
*   [![Image 8: 📰](https://s.w.org/images/core/emoji/17.0.2/svg/1f4f0.svg) Newsletter](https://obsidian.rocks/newsletter/)
*   [![Image 9: ⛏️](https://s.w.org/images/core/emoji/17.0.2/svg/26cf.svg) Resources](https://obsidian.rocks/obsidian-resources/)
*   [![Image 10: ⚙️](https://s.w.org/images/core/emoji/17.0.2/svg/2699.svg) Simple Systems](https://obsidian.rocks/simple-systems-for-obsidian/)

Search for: 

# Quickly Organize Notes in Obsidian

![Image 11](https://obsidian.rocks/wp-content/uploads/2022/08/kelly-sikkema-8jjQ4hmCOcM-unsplash.jpg)

Posted on [August 30, 2022·March 29, 2023](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/) by [Tim Miller](https://obsidian.rocks/author/howlermiller/)

There’s a popular concept in the Obsidian community called _MOCs_, or _[Maps of Content](https://obsidian.rocks/maps-of-content-effortless-organization-for-notes/)_.

What is a MOC? [Pioneered by Nick Milo](https://youtu.be/WUq8Pun28FI), MOCs are notes that primarily link to other notes, giving you an _index_, or a small Table of Contents that you can create for any particular topic. MOCs are one of the best ways to quickly organize notes in Obsidian.

MOCs were revolutionary for me the first time I encountered the idea. It became a _master key_ for me, a single idea that opened up all of the doors and allowed my notes room to grow and flourish.

On This Page [[hide](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#)]

*   [1 Why are MOCs so life-changing?](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#Why-are-MOCs-so-life-changing)
    *   [1.1 Obsidian Changed That](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#Obsidian-Changed-That)

*   [2 The Simplest Way to Build a Map of Content](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#The-Simplest-Way-to-Build-a-Map-of-Content)
*   [3 Refining your MOC](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#Refining-your-MOC)

## Why are MOCs so life-changing?

I’ve always struggled to organize my notes. Every note-taking application has its methods for organization, but none ever clicked with me.

Folders are too rigid, tags too flexible. Time and time again I created a basic structure within a new app, but eventually, I would outgrow it, and start to lose notes. I was never able to maintain more than 500 notes or so before I would abandon the project.

Evernote, Drafts, Notion, Apple Notes, Notepad++: no matter the app, I always had this same fundamental problem.

### Obsidian Changed That

My current Obsidian vault has 4,500+ notes in it.

Does it feel like a chaotic mess? No. Surprisingly (to me), the more notes I create, the _more organized it feels_.

How is that possible? It’s all thanks to linked notes and MOCs.

## The Simplest Way to Build a Map of Content

> Note: This tip requires the use of a community plugin called [Dataview](https://blacksmithgu.github.io/obsidian-dataview/). See [how to use community plugins here](https://obsidian.rocks/how-to-use-community-plugins-in-obsidian/).

I’ve created dozens of MOCs in my vault, and I’ve learned a lot. One of my favorite ways to build a MOC is by using this single-line Dataview query:

```
```dataview
list from [[]] and !outgoing([[]])
```
```

This small line of code is the best way to quickly organize notes in Obsidian. Feel free to copy/paste into your own vault.

Here’s how it works. Say you want to start organizing your notes on Icelandic Ice Fishing. You can create a MOC for that, and add the above query:

![Image 12: An example Ice Fishing MOC](https://i0.wp.com/obsidian.rocks/wp-content/uploads/2022/08/icefishing1.png?w=640&ssl=1)
If you have Dataview installed, you should see this when you click out of that code block:

![Image 13: Dataview showing ‘no results found’.](https://i0.wp.com/obsidian.rocks/wp-content/uploads/2022/08/icefishing2.png?w=640&ssl=1)
Now it’s time to add some content. Maybe you already have some related notes, or maybe not. Regardless, next time you find or add a note related to Icelandic Ice Fishing, simply add a link to the MOC. I like to add it to the top of the note, but you can add it anywhere.

![Image 14: A note about Brown Trout, with a link to the MOC.](https://i0.wp.com/obsidian.rocks/wp-content/uploads/2022/08/icefishing3.png?w=640&ssl=1)![Image 15: A guide to fishing in Iceland, with a link to the MOC.](https://i0.wp.com/obsidian.rocks/wp-content/uploads/2022/08/icefishing4.png?w=640&ssl=1)
Next time you open up your Icelandic Ice Fishing MOC, Dataview will gather all of the linked notes and display them for you.

![Image 16: The Icelandic Ice Fishing MOC with the newly created notes showing up.](https://i0.wp.com/obsidian.rocks/wp-content/uploads/2022/08/icefishing5.png?w=640&ssl=1)
Now that may be enough for you, you can call it a day there. But there’s _another_ step that makes your MOCs _even more useful_.

## Refining your MOC

I like to use this query as an _inbox_, letting me know about new content that I need to sort out further. Once a note appears in my “inbox”, I like to add _supporting content_ to further clarify the purpose of each note. Even better, using the above query, when you _manually_ add a link to your MOC, Dataview will _automatically_ remove it from your inbox.

I usually start by adding headers, and I’ll add even more explanation in paragraphs if necessary. That might look like this:

![Image 17: A finalized MOC with headers for each subtopic.](https://i0.wp.com/obsidian.rocks/wp-content/uploads/2022/08/icefishing6.png?w=640&ssl=1)
And that is the easiest way to quickly organize notes in Obsidian.

> Learn more about MOCs here: [Maps of Content: Effortless organization for notes](https://obsidian.rocks/maps-of-content-effortless-organization-for-notes/)

### Like this:

Like Loading...

[](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/)

[![Image 18: A hand placing a pin on a map.](https://i0.wp.com/obsidian.rocks/wp-content/uploads/2023/03/geojango-maps-Z8UgB80_46w-unsplash.jpg?fit=1200%2C596&ssl=1&resize=350%2C200)](https://obsidian.rocks/maps-of-content-effortless-organization-for-notes/ "Maps of Content: Effortless organization for notes")
#### [Maps of Content: Effortless organization for notes](https://obsidian.rocks/maps-of-content-effortless-organization-for-notes/ "Maps of Content: Effortless organization for notes")

One of the biggest hurdles that you must overcome in order to take good notes is organization. The more notes you take, the harder it is to find things when you need them. A good organization structure will free your mind. Creating notes will become as easy as breathing, and…

March 21, 2023
In "Beginner"

[![Image 19: A notebook that says ](https://i0.wp.com/obsidian.rocks/wp-content/uploads/2023/03/david-iskander-iWTamkU5kiI-unsplash.jpg?fit=1200%2C602&ssl=1&resize=350%2C200)](https://obsidian.rocks/getting-started-with-obsidian-a-beginners-guide/ "Getting Started with Obsidian Notes: A Beginner’s Guide")
#### [Getting Started with Obsidian Notes: A Beginner’s Guide](https://obsidian.rocks/getting-started-with-obsidian-a-beginners-guide/ "Getting Started with Obsidian Notes: A Beginner’s Guide")

Obsidian is a wonderful and potentially life-changing app.But it’s also a complicated app, and getting started with Obsidian notes can be a challenge. If you’re new to Obsidian and not sure where to start, then this is the article for you. What is Obsidian? Obsidian is a beautiful and versatile app…

March 23, 2023
In "About Obsidian"

[![Image 20: Superman just chillin' in the clouds.](https://i0.wp.com/obsidian.rocks/wp-content/uploads/2022/10/mehdi-messrro-1v0JL_wINc-unsplash.jpg?fit=1200%2C800&ssl=1&resize=350%2C200)](https://obsidian.rocks/super-powers-for-obsidian-nine-of-the-best-obsidian-plugins/ "Super Powers for Obsidian: Nine of the Best Obsidian Plugins")
#### [Super Powers for Obsidian: Nine of the Best Obsidian Plugins](https://obsidian.rocks/super-powers-for-obsidian-nine-of-the-best-obsidian-plugins/ "Super Powers for Obsidian: Nine of the Best Obsidian Plugins")

If you're looking to get the most out of your Obsidian experience, then you need to check out the incredible ecosystem of plugins available. These plugins can help you manage tasks, organize your notes automatically, visualize your notes more effectively, make your notes prettier, and so much more. In this…

October 29, 2022
In "About Obsidian"

Posted in [How to](https://obsidian.rocks/category/how-to/)Tagged [dataview](https://obsidian.rocks/tag/dataview/), [howto](https://obsidian.rocks/tag/howto/), [quick tip](https://obsidian.rocks/tag/quick-tip/)
## Post navigation

[Previous:How to Backup Obsidian](https://obsidian.rocks/how-to-backup-obsidian/)

[Next:Obsidian Update 0.16: What’s New and How to Use It](https://obsidian.rocks/obsidian-update-0-16-whats-new-and-how-to-use-it/)

## 19 thoughts on “Quickly Organize Notes in Obsidian”

1.   ![Image 21](https://secure.gravatar.com/avatar/35eabf5d543566b1fafca13a87abf41b4f48d95fe89da9ceae59821977d9cf47?s=32&d=mm&r=g)**JJ**says: [September 11, 2022 at 11:57 am](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-19) Awesome tip! This will make a huge difference to how I organize my vault ![Image 22: 🙂](https://s.w.org/images/core/emoji/17.0.2/svg/1f642.svg) [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-19) 
    1.   ![Image 23](https://secure.gravatar.com/avatar/8e231f6a8278b0812e429de6ae98960abbc492c74dc4110641fecf18fe92cd1f?s=32&d=mm&r=g)**[Timothy Miller](https://obsidian.rocks/)**says: [September 14, 2022 at 11:04 am](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-22) Thanks JJ. Glad to hear it! [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-22) 

2.   ![Image 24](https://secure.gravatar.com/avatar/1acbb4f09f1ddb485c90760fc0839ce0ce02b104bbb843b189a79968604f50a6?s=32&d=mm&r=g)**nitin**says: [February 4, 2023 at 10:48 am](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-556) Excellent use of Dataview. I have a question for you – I end up putting MOCs on blocks within text, which can be linked to via the ^ for transclusion. Do you know if a query like yours can return the block within a linked document where the MOC is referenced?

I’ve been trying to get that, but no luck so far [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-556) 
    1.   ![Image 25](https://secure.gravatar.com/avatar/8e231f6a8278b0812e429de6ae98960abbc492c74dc4110641fecf18fe92cd1f?s=32&d=mm&r=g)**[Timothy Miller](https://obsidian.rocks/)**says: [March 9, 2023 at 10:40 am](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-896) Hi Nitin. I’m not sure I understand what you’re trying to do here: I would recommend asking on the help form ([https://forum.obsidian.md/c/get-help/](https://forum.obsidian.md/c/get-help/)) and including a few more details. [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-896) 

3.   ![Image 26](https://secure.gravatar.com/avatar/bb47fef77f1c6635c7bdc529d1629e69cacdaccddc5be1bf75e1020bf370c887?s=32&d=mm&r=g)**Kamil**says: [March 7, 2023 at 8:54 am](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-895) Hi. Do you store your MOC notes in permanent folder or in a separate MOCs folder? [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-895) 
    1.   ![Image 27](https://secure.gravatar.com/avatar/8e231f6a8278b0812e429de6ae98960abbc492c74dc4110641fecf18fe92cd1f?s=32&d=mm&r=g)**[Timothy Miller](https://obsidian.rocks/)**says: [March 9, 2023 at 12:52 pm](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-899) I store them in my permanent folder with all of my other permanent notes. I do give each MOC a tag, #MOC, which allows me to look at them all if I need to (using search or Dataview), but I rarely use it.

I honestly rarely think about file structure, because I so rarely use the file picker. I’m almost always navigating my notes via links, not via folders, so I try to keep my folders as simple as possible. [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-899) 

4.   ![Image 28](https://secure.gravatar.com/avatar/401c1bdff6f42a05defd94e6323791f2a854f51e8ad3aacb280d45cbb1777bb5?s=32&d=mm&r=g)**KK**says: [May 25, 2023 at 7:37 am](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-1644) Any way of sorting the linked notes in MOCs so the oldest added is on top and the newest on bottom? [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-1644) 
    1.   ![Image 29](https://secure.gravatar.com/avatar/8e231f6a8278b0812e429de6ae98960abbc492c74dc4110641fecf18fe92cd1f?s=32&d=mm&r=g)**[Timothy Miller](https://obsidian.rocks/)**says: [May 25, 2023 at 4:04 pm](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-1647) Yep! If you are using Dataview. You can add a SORT to any query. You can sort based on creation date by adding this:

`SORT file.ctime DESC`

You can learn about a bunch of different ways to tweak your queries like this in our [introduction to Dataview](http://obsidian.rocks/dataview-in-obsidian-a-beginners-guide/). [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-1647) 

5.   ![Image 30](https://secure.gravatar.com/avatar/0f755716c9a8a75246ee34d659464320d5174d4581458596a6f4b0cc7c37175d?s=32&d=mm&r=g)**LEONARDO MELIA**says: [September 14, 2023 at 5:53 am](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-2541) what effect provokes the esclamation mark before outgoing function? [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-2541) 
    1.   ![Image 31](https://secure.gravatar.com/avatar/8e231f6a8278b0812e429de6ae98960abbc492c74dc4110641fecf18fe92cd1f?s=32&d=mm&r=g)**[Timothy Miller](https://obsidian.rocks/)**says: [September 14, 2023 at 9:23 am](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-2542) That means “not”. So `!outgoing([[]])` in effect means “do NOT include links that already exist in this file”. If you remove that, then Dataview will list all links that link to your file, whether they already exist or not.

It’s a little bit obscure, which is why I wrote this article. Hope that helps! [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-2542) 
        1.   ![Image 32](https://secure.gravatar.com/avatar/dbbddaf210babe1cc958a84e43e4c73ed671daac5032be3cccc11fa12db888f8?s=32&d=mm&r=g)**Shane**says: [November 25, 2024 at 11:38 am](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-26703) Great ideas Timothy. One suggestion I have is to explain the code in the main body of the article. You give an example, but you don’t actually explain what the code means. [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-26703) 

6.   ![Image 33](https://secure.gravatar.com/avatar/235c45e81e3dc425960a8164fd2018e086b291bfe06d4a4398f7dc451786f138?s=32&d=mm&r=g)**Bart van Elderen**says: [September 22, 2023 at 3:49 pm](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-2573) I am an absolute beginner, and I could understand using dataview to generate the content of a moc but I really don’t get what you are trying to explain with ‘Refining your MOC’? What do you do when you say ‘I like to use this query as an inbox’ and ‘using the above query, when you manually add a link to your MOC’? Could you explain it step by step?

 Thanks! [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-2573) 
    1.   ![Image 34](https://secure.gravatar.com/avatar/8e231f6a8278b0812e429de6ae98960abbc492c74dc4110641fecf18fe92cd1f?s=32&d=mm&r=g)**[Timothy Miller](https://obsidian.rocks/)**says: [September 25, 2023 at 9:29 am](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-2587) Hi Bart! Sure. The issue with the above Dataview query is that it’s not organized. It creates an unordered list of notes that link to that MOC. It’s handy for finding lost notes, but I find it isn’t helpful once the list becomes longer than 6 or so items.

So when I open an MOC that has more than 6 “unorganized” notes, I try to sort them into more logical groupings. The nice thing about the above query is that it automatically updates, so any link you add to the MOC will automatically be removed from the Dataview list.

So my process goes something like this:

 – Add new notes to my vault, link to relevant MOCs

 – When referencing an MOC, check the “unsorted” links

 – If there are more than ~6 unsorted links, create supporting content, such as headers and logical groupings of similar ideas [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-2587) 
        1.   ![Image 35](https://secure.gravatar.com/avatar/ccd345381e448f4f5c7db5abcbf1e51e642982aa18a4d55cfaef458c68ea7b4a?s=32&d=mm&r=g)**errant_almond**says: [October 31, 2023 at 3:31 am](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-2816) Does this mean that in order to subdivide the list by categories, you have to link to the header for that section within the MOC document rather than just the MOC document itself?

 So, when you decide to put those six notes under a new heading, you edit the link on all of the manually, correct?

Thanks!

 Love this query. It is helping me make the transition from just folders to…something else. [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-2816) 
            1.   ![Image 36](https://secure.gravatar.com/avatar/8e231f6a8278b0812e429de6ae98960abbc492c74dc4110641fecf18fe92cd1f?s=32&d=mm&r=g)**[Tim Miller](https://obsidian.rocks/)**says: [October 31, 2023 at 9:22 am](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-2818) Correct: the goal of this query is to make it easy for you to create MOCs. The query creates a self-updating “inbox”, which allows you to see _unsorted_ files and sort them into relevant sections of your note. The goal is ultimately to sort the files, the query just makes that easier ![Image 37: 🙂](https://s.w.org/images/core/emoji/17.0.2/svg/1f642.svg) [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-2818) 
                1.   ![Image 38](https://secure.gravatar.com/avatar/ccd345381e448f4f5c7db5abcbf1e51e642982aa18a4d55cfaef458c68ea7b4a?s=32&d=mm&r=g)**[errant_almond](http://-/)**says: [October 31, 2023 at 10:30 pm](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-2822) Thanks for the quick reply. I think in stepping away from folders, it takes an extra night of sleep of moment of realization to see that a query like this is what you said, rather than a way to automatically display your _folder directory_, which is the initial instinct, haha. 
                2.   ![Image 39](https://secure.gravatar.com/avatar/8e231f6a8278b0812e429de6ae98960abbc492c74dc4110641fecf18fe92cd1f?s=32&d=mm&r=g)**[Tim Miller](https://obsidian.rocks/)**says: [November 2, 2023 at 9:32 am](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-2825) Ha, that’s a good point! I struggled to abandon folder structure at first too. I’m glad you reminded me of that hurdle. 

7.   ![Image 40](https://secure.gravatar.com/avatar/ac4bb4ffa671fad30f91a9c3035d7463da176ac04feb5f4aca55567f8bf1ee33?s=32&d=mm&r=g)**Nick R**says: [January 25, 2024 at 1:40 pm](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-3788) Hi Tim thanks so much for this! I was wondering say you wanted to have 2 notes which are composed of notes from 2 different books. Each of these books has similar themes and you wanted to basically create a document that combined relevant notes (with say something like a hashtag) is that possible under this system. Like I want to keep all the notes from a single book together but would want to try and create a third document based on the themes across each book.

So I think about it we have:

 Note A for Book A

 Note B for Book B

Within Note A:

 Note A1 with #Theme1 (basically this is just a random blurb or highlighted section of the book with a # based on the topic)

 Note A2 with #Theme2

Within Note B

 Note B1 with #Theme1

 Note B2 with #Theme2

What type of Querry or system could create

Note C based on #Theme1

 Note A1

 Note B1 [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-3788) 
8.   ![Image 41](https://secure.gravatar.com/avatar/376bfbfe39be3cffbbfdf1f27483e0c7dd82710f8d0b4d15af030a382266965d?s=32&d=mm&r=g)**Alejandro Tendero**says: [October 20, 2025 at 3:26 pm](https://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-36909) Hi Tim,

I think this could be interesting for anyone who has a Home Note containing links to the MOCs. If the note containing the links to the MOCs is called “Home Note”, the query could be as follows:

```
LIST
FROM [[]] AND !outgoing([[]]) AND !"Home Note"
```

This way the query doesn’t return the Home Note, which contains a link to the MOC. [Reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#comment-36909) 

### Leave a Reply [Cancel reply](http://obsidian.rocks/quick-tip-quickly-organize-notes-in-obsidian/#respond)

Your email address will not be published.Required fields are marked *

Comment *

Name *

Email *

Website

- [x] Save my name, email, and website in this browser for the next time I comment.

- [x] Notify me of follow-up comments by email.

### Join the Newsletter

Subscribe for my latest news and updates, and for a FREE Read-it-later system for Obsidian..

No spam. Unsubscribe at any time.

Name 

Email 

HP 

 Obsidian Rocks is not affiliated with Obsidian. We're just big fans!  | 

[Obsidian Rocks](https://obsidian.rocks/?blackhole=50762a3e7d "Do NOT follow this link or you will be banned from the site!")

%d

![Image 42](https://pixel.wp.com/g.gif?v=ext&blog=215569054&post=70&tz=-5&srv=obsidian.rocks&j=1%3A14.8&host=obsidian.rocks&ref=&fcp=0&rand=0.12119285834917748)

