// Root of every locale is the landing page. The actual content lives in
// the pricing route's client component so the marketing surface stays a
// single source of truth — `/` and `/pricing` render the same screen,
// with `/pricing` doubling as a deep link to the comparison/cards section.
// When the user signs in, the (app)/* segment takes over and they jump
// straight to /dashboard from any nav action.
export { default } from "./pricing/page";
