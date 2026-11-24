# Folding and printer practice sheets

Print one PDF on one side of one sheet, using the named paper size and **Actual size / 100%**. A4 side-fold uses a portrait sheet; A4 top-fold uses a landscape sheet. The Legal side-fold sample uses a portrait Legal sheet with minimum margins left 5, right 8, top 5, bottom 10 mm.

Measure the ruler between its end ticks: 100 mm. Check that the printable-area rectangle is visible, then hold the printed side facing you and follow the guide numbers.

| Sheet | First fold | Second fold | Finished card |
| --- | --- | --- | --- |
| A4 side fold | Top half behind bottom half | Left half behind right half | 105 x 148.5 mm |
| A4 top fold | Left half behind right half | Top half behind bottom half | 148.5 x 105 mm |
| Legal side fold | Top half behind bottom half | Left half behind right half | 107.95 x 177.8 mm |

The closed front, closed back, and opened inside should all read upright. The blank side of the sheet becomes hidden between layers. No second-side printing is needed. These are test sheets; choose **Card** in the app to print your actual design, with printed fold guides disabled for the finished card.

Create other tests in **Print / PDF > What to print > Folding and printer test**, or use:

```bash
python3 main.py --test-page --fold top --paper Legal --export practice.pdf
```
