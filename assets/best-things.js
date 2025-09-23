/* FILE: assets/best-things.js
 *
 * Adds interactive "Best Things to Do in Muscat" section inspired by bestdubai.com.
 * Provides tabs (Eat, Play, Explore) and renders a featured listing plus
 * top five additional listings for each category. Data is defined statically
 * here for simplicity; real implementations could fetch from an API or JSON.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Safety: only run on pages that actually have the section
  if (!document.getElementById('best-things')) return;
  
  // Data definitions for each category. Images reference local assets.
  const bestThingsData = {
    eat: {
      featured: {
        rank: '#1 Restaurants in Muscat',
        name: 'Spice Route Restaurant',
        location: 'Muttrah',
        status: 'open',
        price: '$$$',
        type: 'Omani',
        description: 'Spice Route serves traditional Omani dishes seasoned with aromatic spices, accompanied by live oud music and warm hospitality.',
        verified: true,
        overall: 9.46,
        scores: {
          'Food Quality': 9.65,
          'Service': 9.85,
          'Ambience': 9.60,
          'Value for Money': 8.90,
          'Amenities': 9.20
        },
        image: 'assets/images/featured-eat.png'
      },
      top: [
        {
          rankBadge: 'Top 5 in Restaurants',
          name: 'Seafood Grill',
          location: 'Shatti Al‑Qurum',
          status: 'open',
          price: '$$$',
          type: 'Seafood',
          score: 9.34,
          image: 'assets/images/restaurants.png'
        },
        {
          rankBadge: 'Top 5 in Restaurants',
          name: 'Garden Cafe',
          location: 'Muttrah',
          status: 'open',
          price: '$$',
          type: 'Cafe',
          score: 9.32,
          image: 'assets/images/restaurants.png'
        },
        {
          rankBadge: 'Top 5 in Restaurants',
          name: 'Dessert House',
          location: 'Al Khuwair',
          status: 'open',
          price: '$$',
          type: 'Dessert',
          score: 9.27,
          image: 'assets/images/restaurants.png'
        },
        {
          rankBadge: 'Top 5 in Restaurants',
          name: 'Mediterranean Kitchen',
          location: 'Al Mouj',
          status: 'open',
          price: '$$$',
          type: 'Mediterranean',
          score: 9.23,
          image: 'assets/images/restaurants.png'
        },
        {
          rankBadge: 'Top 5 in Restaurants',
          name: 'Omani House',
          location: 'Ruwi',
          status: 'open',
          price: '$$',
          type: 'Omani',
          score: 9.21,
          image: 'assets/images/restaurants.png'
        }
      ]
    },
    play: {
      featured: {
        rank: '#1 Spas in Muscat',
        name: 'Lotus Spa',
        location: 'Qurum',
        status: 'open',
        price: '$$$',
        type: 'Spa',
        description: 'Lotus Spa offers holistic relaxation with luxurious treatments inspired by Omani traditions.',
        verified: true,
        overall: 9.40,
        scores: {
          'Quality': 9.60,
          'Service': 9.70,
          'Ambience': 9.50,
          'Value for Money': 8.80,
          'Amenities': 9.10
        },
        image: 'assets/images/featured-play.png'
      },
      top: [
        {
          rankBadge: 'Top 5 in Spas',
          name: 'Blue Lagoon Spa',
          location: 'Al Khuwair',
          status: 'open',
          price: '$$$',
          type: 'Spa',
          score: 9.28,
          image: 'assets/images/spas.png'
        },
        {
          rankBadge: 'Top 5 in Spas',
          name: 'Harmony Spa',
          location: 'Seeb',
          status: 'open',
          price: '$$',
          type: 'Spa',
          score: 9.25,
          image: 'assets/images/spas.png'
        },
        {
          rankBadge: 'Top 5 in Spas',
          name: 'Oasis Spa',
          location: 'Madinat Sultan Qaboos',
          status: 'open',
          price: '$$',
          type: 'Spa',
          score: 9.22,
          image: 'assets/images/spas.png'
        },
        {
          rankBadge: 'Top 5 in Spas',
          name: 'Royal Hammam Spa',
          location: 'Qurum',
          status: 'open',
          price: '$$$',
          type: 'Spa',
          score: 9.18,
          image: 'assets/images/spas.png'
        },
        {
          rankBadge: 'Top 5 in Spas',
          name: 'Palm Retreat Spa',
          location: 'Al Mouj',
          status: 'open',
          price: '$$$',
          type: 'Spa',
          score: 9.15,
          image: 'assets/images/spas.png'
        }
      ]
    },
    explore: {
      featured: {
        rank: '#1 Places to Explore in Muscat',
        name: 'The Chedi Muscat',
        location: 'Al Azaiba',
        status: 'open',
        price: '$$$$',
        type: 'Resort',
        description: 'The Chedi Muscat combines Omani architecture with contemporary luxury, offering serene gardens, private beach access and world‑class amenities.',
        verified: true,
        overall: 9.50,
        scores: {
          'Quality': 9.70,
          'Service': 9.80,
          'Ambience': 9.65,
          'Value for Money': 8.85,
          'Amenities': 9.30
        },
        image: 'assets/images/featured-explore.png'
      },
      top: [
        {
          rankBadge: 'Top 5 in Explore',
          name: 'Al Bustan Palace',
          location: 'Muttrah',
          status: 'open',
          price: '$$$$',
          type: 'Resort',
          score: 9.40,
          image: 'assets/images/hotels.png'
        },
        {
          rankBadge: 'Top 5 in Explore',
          name: 'Muscat City Centre',
          location: 'Seeb',
          status: 'open',
          price: '$$',
          type: 'Mall',
          score: 9.35,
          image: 'assets/images/malls.png'
        },
        {
          rankBadge: 'Top 5 in Explore',
          name: 'Desert Oasis Resort',
          location: 'Near Muscat',
          status: 'open',
          price: '$$$',
          type: 'Resort',
          score: 9.30,
          image: 'assets/images/hotels.png'
        },
        {
          rankBadge: 'Top 5 in Explore',
          name: 'Muscat Grand Mall',
          location: 'Al Khuwayr',
          status: 'open',
          price: '$$',
          type: 'Mall',
          score: 9.25,
          image: 'assets/images/malls.png'
        },
        {
          rankBadge: 'Top 5 in Explore',
          name: 'Palm Grove Hotel',
          location: 'Qurum',
          status: 'open',
          price: '$$$',
          type: 'Hotel',
          score: 9.20,
          image: 'assets/images/hotels.png'
        }
      ]
    }
  };

  // Elements
  const featuredEl = document.getElementById('featured-card');
  const listingsEl = document.getElementById('top-listings');

  /**
   * Renders the featured card for the given category.
   * @param {Object} item
   */
  function renderFeatured(item) {
    const scoreLines = Object.keys(item.scores)
      .map(label => {
        const val = item.scores[label].toFixed(2);
        // Insert a non‑breaking space between the label and value for readability
        return `<span><span>${label}</span>&nbsp;<span>${val}</span></span>`;
      })
      .join('');
    featuredEl.innerHTML = `
      <img src="${item.image}" alt="">
      <div class="content">
        <div class="rank">${item.rank}</div>
        <h3 class="name">${item.name}</h3>
        <div class="meta">
          <span>${item.location}</span> ·
          <span>${item.status === 'open' ? '<span class="status open">Open</span>' : '<span class="status closed">Closed</span>'}</span> ·
          <span>${item.price}</span> ·
          <span>${item.type}</span>
        </div>
        <p class="desc">${item.description}</p>
        <div class="score-box">
          <div class="score-summary">${item.overall.toFixed(2)}<small>/10</small></div>
          <div class="score-breakdown">${scoreLines}</div>
        </div>
      </div>
    `;
  }

  /**
   * Renders the top listing cards for the given category.
   * @param {Array} list
   */
  function renderListings(list) {
    listingsEl.innerHTML = list.map(item => {
      const statusClass = item.status === 'open' ? 'open' : 'closed';
      const statusLabel = item.status === 'open' ? 'Open' : 'Closed';
      return `
        <div class="listing-card">
          <img src="${item.image}" alt="">
          <div class="info">
            <div class="name">${item.name}</div>
            <div class="sub">${item.location} · ${item.price} · ${item.type}</div>
            <div class="status ${statusClass}">${statusLabel}</div>
          </div>
          <div class="score">${item.score.toFixed(2)}</div>
        </div>
      `;
    }).join('');
  }

  /**
   * Loads a category by slug and renders both featured and listings.
   * @param {string} cat
   */
  function loadCategory(cat) {
    const data = bestThingsData[cat];
    if (!data) return;
    renderFeatured(data.featured);
    renderListings(data.top);
  }

  // Attach events to tabs
  const tabBtns = document.querySelectorAll('#best-things .tab');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const cat = btn.dataset.cat;
      loadCategory(cat);
    });
  });

  // Initial load
  loadCategory('eat');
});
