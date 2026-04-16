/**
 * Submits the first form on the page
 **/
function pauseFirstForm(home) {
	
	var f = document.getElementsByTagName("form");	
	// no one has put the id on the form
	//submitFormNewAction(f[0].id, newAction)

	if(f.length > 0) {
		f[0].action = addPathInfo(f[0].action)
		f[0].submit()
	} else {
		document.location = home;
	}
}

function addPathInfo(linkString){	
	linkString += "/pause/pause";
	return linkString;
}


/**
* Submit a from with a new action
**/
function submitFormNewAction(formId, action) {
	var f = document.getElementById(formId)
	f.action = action
	f.submit()
}

/**
* Allows you to submit a form without a button
**/
function submitForm(formId) {
	var f = document.getElementById(formId)	
	f.submit()
}

/**
* Allows you to change the action of a form
**/
function changeFormAction(formId, action) {
	var f = document.getElementById(formId)	
	f.action = action
}

/**
* Allows you to submit a form without a button
**/
function changeValue(elId, newvalue) {
	var e = document.getElementById(elId)	
	e.value=newvalue;
}

/**
* Pop up a picture in a new window
**/
function popUpPicture(url, title) {
  	window.open(url, "test", 'toolbar=0,scrollbars=1,location=0,statusbar=0,menubar=0,resizable=1,width=800,height=600,left = 112,top = 50');
}

/*
 * POPUP HELP SCRIPT 
 * NEED TO MAKE THIS x-BROWSER COMPATIBLE
 *
**/

function showElement(elId, linkEl) {
	return positionElement(elId, getRightEdge(linkEl) + 5, getTopEdge(linkEl));
}

function hideElement(elId, linkEl) {
	return positionElement(elId, -9999, -9999);
}

function positionElement(elId, left, top) {
	if (document.getElementById) {
		var el = document.getElementById(elId);
		el.style.left = left + "px";
		el.style.top = top + "px";
	}
	return false;
}

function getLeftEdge(el) {
	return el.offsetLeft;
}

function getTopEdge(el) {
	return el.offsetTop;
}

function getRightEdge(el) {
	return getLeftEdge(el) + parseInt(el.offsetWidth);
}

function getSelectedOptionValue(ele) {
	return ele.options[ele.selectedIndex].value
}

function getSelectedOptionText(ele) {
	return ele.options[ele.selectedIndex].text
}

function populateElementWithSelection(selectInput, textInputId) {
	var destination =  document.getElementById(textInputId)
	destination.value = getSelectedOptionValue(selectInput)
}

/**
* Populate another date field with greater date
**/
function getOtherDate(dateField, id)
{	
		var idStr = id;
		var str=dateField.value;
		var strYear = str.substr(6,4);
		var strMonth = str.substr(3,2);
		var strDay = str.substr(0,2);				
		var value1 = parseInt(strDay) + 9;
		
		var d4 = new Date();		
		d4.setFullYear(strYear);
		d4.setMonth(strMonth - 1); // 0 based 
		d4.setDate(value1); // 0 -31
		
		var varNewStr = d4.getDate() + '/' + (d4.getMonth()+1) + '/' + d4.getFullYear();		
		
		document.getElementById(idStr).value=varNewStr;				
}	

function populateFromTo(date, tabs)
{
	document.getElementById('bookeventformstartdate').value=date;
	document.getElementById('bookeventformenddate').value=date;
	showOneDiv('EventDetails',tabs);
}

